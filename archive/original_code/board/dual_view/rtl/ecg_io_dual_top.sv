// AXI-Lite ADC acquisition and HDMI waveform memory. All ADC control outputs
// reset to CS=1, SCLK=0, START=0, RESET_N=1. Automatic acquisition defaults OFF.
module ecg_io_dual_top #(
    parameter integer FIFO_AW=10,
    parameter integer DEBOUNCE_CYCLES=2000000,
    parameter integer SPI_CS_WAIT=1000
)(
    (* X_INTERFACE_PARAMETER="XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *) input wire s_axi_aclk,
    (* X_INTERFACE_PARAMETER="XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *) input wire s_axi_aresetn,
    input wire [15:0] s_axi_awaddr,
    input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input wire [15:0] s_axi_araddr,input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,input wire s_axi_rready,
    input wire ads_dout,ads_drdy_n,
    output wire ads_cs_n,ads_sclk,ads_din,ads_start,ads_pwdn_reset_n,
    input wire [3:0] buttons,
    input wire sw0,
    input wire hdmi_hpd,
    (* X_INTERFACE_PARAMETER="XIL_INTERFACENAME pixel_clk, ASSOCIATED_RESET pixel_resetn, FREQ_HZ 25200000" *)
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 pixel_clk CLK" *) input wire pixel_clk,
    (* X_INTERFACE_PARAMETER="XIL_INTERFACENAME pixel_resetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 pixel_resetn RST" *) input wire pixel_resetn,
    output wire [23:0] video_rgb,
    output wire video_hsync,video_vsync,video_de
);
    reg [15:0] aw_hold,ar_hold;
    reg [31:0] w_hold;
    reg [3:0] ws_hold;
    reg aw_pending,w_pending,read_pending,read_had_data;
    wire write_commit=aw_pending && w_pending && !s_axi_bvalid;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!read_pending && !s_axi_rvalid;
    reg [7:0] control;
    reg [15:0] divider;
    reg [127:0] command_tx,command_rx,spi_tx;
    reg [4:0] spi_length;
    reg spi_start,auto_inflight,command_done;
    wire spi_busy,spi_done;
    wire [127:0] spi_rx;
    (* ASYNC_REG="TRUE" *) reg miso_meta,miso_sync,drdy_meta,drdy_sync;
    reg drdy_previous;
    wire drdy_falling=drdy_previous && !drdy_sync;
    assign ads_start=control[1];assign ads_pwdn_reset_n=control[0];
    ads_spi_engine #(.CS_WAIT(SPI_CS_WAIT)) spi(
        .clk(s_axi_aclk),.resetn(s_axi_aresetn),.start(spi_start),
        .tx(spi_tx),.length(spi_length),.half_period(divider),.miso(miso_sync),
        .busy(spi_busy),.done(spi_done),.rx(spi_rx),
        .cs_n(ads_cs_n),.sclk(ads_sclk),.mosi(ads_din));

    localparam integer FIFO_DEPTH=(1<<FIFO_AW);
    (* ram_style="block" *) reg [71:0] fifo [0:FIFO_DEPTH-1];
    reg [FIFO_AW-1:0] wr_ptr,rd_ptr;
    reg [FIFO_AW:0] fifo_count;
    wire [10:0] fifo_count_11=fifo_count;
    reg [71:0] read_frame;
    reg [31:0] frame_count,overrun_count,bad_frame_count;
    wire [71:0] frame_bytes={spi_rx[7:0],spi_rx[15:8],spi_rx[23:16],
                            spi_rx[31:24],spi_rx[39:32],spi_rx[47:40],
                            spi_rx[55:48],spi_rx[63:56],spi_rx[71:64]};
    wire valid_frame=(frame_bytes[71:68]==4'hc);
    wire new_frame=spi_done && auto_inflight;
    wire fifo_pop=s_axi_rvalid && s_axi_rready && ar_hold==16'h0028 && read_had_data;
    wire fifo_push=new_frame && valid_frame && (fifo_count<FIFO_DEPTH || fifo_pop);
    wire clear_fifo=write_commit && aw_hold==0 && ws_hold[0] && w_hold[3];
    wire drdy_missed=control[2] && drdy_falling && (spi_busy || spi_start || fifo_count==FIFO_DEPTH);

    (* ASYNC_REG="TRUE" *) reg [3:0] btn_meta,btn_sync;
    reg [3:0] btn_stable;
    reg [21:0] debounce [0:3];
    reg [3:0] btn_press;
    (* ASYNC_REG="TRUE" *) reg sw_meta,sw_sync;
    reg sw_stable;
    reg [21:0] sw_debounce;
    reg selected_channel,selected_path,freeze_display;
    reg [1:0] display_flags;
    reg frame_request;
    wire frame_active;
    (* ASYNC_REG="TRUE" *) reg frame_ack_meta,frame_ack_sync;
    wire frame_pending=frame_request!=frame_ack_sync;
    (* ASYNC_REG="TRUE" *) reg hpd_meta,hpd_sync;
    integer j;
    function automatic [31:0] merge_bytes(input [31:0] previous,input [31:0] data,input [3:0] enables);
        integer b;
        begin
            merge_bytes=previous;
            for(b=0;b<4;b=b+1) if(enables[b])merge_bytes[b*8+:8]=data[b*8+:8];
        end
    endfunction
    wire wave_we=write_commit && aw_hold>=16'h4000 && aw_hold<16'h6800 &&
                 aw_hold[1:0]==0 && ws_hold==4'hf && !frame_pending;
    wire [11:0] wave_addr=(aw_hold-16'h4000)>>2;
    wire label_we=write_commit && aw_hold>=16'h7000 && aw_hold<16'h9800 &&
                  aw_hold[1:0]==0 && ws_hold==4'hf && !frame_pending;
    wire hud_we=write_commit && aw_hold>=16'ha000 && aw_hold<16'haa00 &&
                aw_hold[1:0]==0 && ws_hold==4'hf && !frame_pending;
    wire [11:0] video_addr=hud_we?((aw_hold-16'ha000)>>2):(label_we?((aw_hold-16'h7000)>>2):wave_addr);
    wire [23:0] rgb_native;
    // Digilent rgb2dvi expects R,B,G byte ordering, rather than standard R,G,B.
    assign video_rgb={rgb_native[23:16],rgb_native[7:0],rgb_native[15:8]};
    ecg_wave_video video(
        .bus_clk(s_axi_aclk),.wave_we(wave_we),.label_we(label_we),.hud_we(hud_we),.wave_addr(video_addr),.wave_data(w_hold[19:0]),
        .wave_write_bank(!frame_ack_sync),.frame_request(frame_request),.frame_active(frame_active),
        .pixel_clk(pixel_clk),.pixel_resetn(pixel_resetn),
        .selection({freeze_display,selected_path,selected_channel}),.dual_view(sw_stable),.display_flags(display_flags),
        .rgb(rgb_native),.hsync(video_hsync),.vsync(video_vsync),.de(video_de));

    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            miso_meta<=0;miso_sync<=0;drdy_meta<=1;drdy_sync<=1;drdy_previous<=1;
            btn_meta<=0;btn_sync<=0;btn_stable<=0;btn_press<=0;
            sw_meta<=0;sw_sync<=0;sw_stable<=0;sw_debounce<=0;
            hpd_meta<=0;hpd_sync<=0;
            frame_ack_meta<=0;frame_ack_sync<=0;
            for(j=0;j<4;j=j+1)debounce[j]<=0;
        end else begin
            miso_meta<=ads_dout;miso_sync<=miso_meta;
            hpd_meta<=hdmi_hpd;hpd_sync<=hpd_meta;
            frame_ack_meta<=frame_active;frame_ack_sync<=frame_ack_meta;
            drdy_meta<=ads_drdy_n;drdy_sync<=drdy_meta;drdy_previous<=drdy_sync;
            btn_meta<=buttons;btn_sync<=btn_meta;btn_press<=0;
            sw_meta<=sw0;sw_sync<=sw_meta;
            if(sw_sync==sw_stable)sw_debounce<=0;
            else if(sw_debounce==DEBOUNCE_CYCLES-1)begin sw_stable<=sw_sync;sw_debounce<=0;end
            else sw_debounce<=sw_debounce+1;
            for(j=0;j<4;j=j+1) begin
                if(btn_sync[j]==btn_stable[j]) debounce[j]<=0;
                else if(debounce[j]==DEBOUNCE_CYCLES-1) begin
                    debounce[j]<=0;btn_stable[j]<=btn_sync[j];
                    if(btn_sync[j])btn_press[j]<=1;
                end else debounce[j]<=debounce[j]+1;
            end
        end
    end

    // True dual-port RAM: one synchronous ADC write and one synchronous AXI read.
    always @(posedge s_axi_aclk) begin
        if(fifo_push && !clear_fifo) fifo[wr_ptr]<=frame_bytes;
        if(s_axi_arvalid && s_axi_arready) read_frame<=fifo[rd_ptr];
    end
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn || clear_fifo) begin
            wr_ptr<=0;rd_ptr<=0;fifo_count<=0;frame_count<=0;overrun_count<=0;bad_frame_count<=0;
        end else begin
            if(fifo_push) wr_ptr<=wr_ptr+1;
            if(fifo_pop) rd_ptr<=rd_ptr+1;
            case({fifo_push,fifo_pop})
              2'b10:fifo_count<=fifo_count+1;
              2'b01:fifo_count<=fifo_count-1;
              default:;
            endcase
            if(new_frame) frame_count<=frame_count+1;
            if(new_frame && !valid_frame) bad_frame_count<=bad_frame_count+1;
            if(drdy_missed || (new_frame && valid_frame && !fifo_push))overrun_count<=overrun_count+1;
        end
    end
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            aw_pending<=0;w_pending<=0;aw_hold<=0;w_hold<=0;ws_hold<=0;
            ar_hold<=0;read_pending<=0;read_had_data<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            control<=1;divider<=89;command_tx<=0;command_rx<=0;
            spi_tx<=0;spi_length<=0;spi_start<=0;auto_inflight<=0;command_done<=0;
            selected_channel<=0;selected_path<=0;freeze_display<=0;display_flags<=1;
            frame_request<=0;
        end else begin
            spi_start<=0;
            if(btn_press[0])selected_channel<=0;
            if(btn_press[1])selected_channel<=1;
            if(btn_press[2])selected_path<=!selected_path;
            if(btn_press[3])freeze_display<=!freeze_display;
            if(spi_done && !auto_inflight)begin command_rx<=spi_rx;command_done<=1;end
            if(control[2] && drdy_falling && !spi_busy && !spi_start && fifo_count<FIFO_DEPTH)begin
                spi_tx<=0;spi_length<=9;spi_start<=1;auto_inflight<=1;
            end
            if(s_axi_awvalid && s_axi_awready)begin aw_hold<=s_axi_awaddr;aw_pending<=1;end
            if(s_axi_wvalid && s_axi_wready)begin w_hold<=s_axi_wdata;ws_hold<=s_axi_wstrb;w_pending<=1;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(write_commit)begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(aw_hold[1:0]!=0)s_axi_bresp<=2;
                else if((aw_hold>=16'h4000 && aw_hold<16'h6800) || (aw_hold>=16'h7000 && aw_hold<16'h9800) || (aw_hold>=16'ha000 && aw_hold<16'haa00))begin
                    if(ws_hold!=4'hf || frame_pending)s_axi_bresp<=2;
                end else case(aw_hold)
                16'h0000: if(ws_hold[0])control<=w_hold[7:0]&8'h07;
                16'h0008: begin
                    if(!ws_hold[0] || spi_busy || spi_start || control[2] || w_hold[4:0]==0 || w_hold[4:0]>16)
                        s_axi_bresp<=2;
                    else begin spi_tx<=command_tx;spi_length<=w_hold[4:0];spi_start<=1;auto_inflight<=0;command_done<=0;end
                end
                16'h000c: if(ws_hold[0] && ws_hold[1] && w_hold[15:0]>=4) divider<=w_hold[15:0];
                16'h0014: if(ws_hold[0])begin selected_channel<=w_hold[0];selected_path<=w_hold[1];freeze_display<=w_hold[2];end
                16'h0018: if(ws_hold[0])display_flags<=w_hold[1:0];
                16'h001c: begin
                    if(!ws_hold[0] || frame_pending)s_axi_bresp<=2;
                    else frame_request<=w_hold[0];
                end
                16'h0100:command_tx[31:0]<=merge_bytes(command_tx[31:0],w_hold,ws_hold);
                16'h0104:command_tx[63:32]<=merge_bytes(command_tx[63:32],w_hold,ws_hold);
                16'h0108:command_tx[95:64]<=merge_bytes(command_tx[95:64],w_hold,ws_hold);
                16'h010c:command_tx[127:96]<=merge_bytes(command_tx[127:96],w_hold,ws_hold);
                default:s_axi_bresp<=2;
                endcase
            end
            if(s_axi_arvalid && s_axi_arready)begin
                ar_hold<=s_axi_araddr;read_pending<=1;read_had_data<=(fifo_count!=0);
            end
            if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
            if(read_pending)begin
                read_pending<=0;s_axi_rvalid<=1;s_axi_rdata<=0;s_axi_rresp<=0;
                if(ar_hold[1:0]!=0)s_axi_rresp<=2;
                else case(ar_hold)
                16'h0000:s_axi_rdata<={24'd0,control};
                16'h0004:s_axi_rdata<={5'd0,fifo_count_11,12'd0,(bad_frame_count!=0),(overrun_count!=0),command_done,spi_busy|spi_start};
                16'h000c:s_axi_rdata<={16'd0,divider};
                16'h0010:s_axi_rdata<={20'd0,btn_sync,5'd0,freeze_display,selected_path,selected_channel};
                16'h0014:s_axi_rdata<={29'd0,freeze_display,selected_path,selected_channel};
                16'h0018:s_axi_rdata<={30'd0,display_flags};
                16'h0020:s_axi_rdata<=read_had_data?{8'd0,read_frame[71:48]}:0;
                16'h0024:s_axi_rdata<=read_had_data?{{8{read_frame[47]}},read_frame[47:24]}:0;
                16'h0028:s_axi_rdata<=read_had_data?{{8{read_frame[23]}},read_frame[23:0]}:0;
                16'h002c:s_axi_rdata<=frame_count;
                16'h0030:s_axi_rdata<=overrun_count;
                16'h0034:s_axi_rdata<=bad_frame_count;
                16'h0038:s_axi_rdata<={31'd0,hpd_sync};
                16'h0200:s_axi_rdata<=command_rx[31:0];
                16'h0204:s_axi_rdata<=command_rx[63:32];
                16'h0208:s_axi_rdata<=command_rx[95:64];
                16'h020c:s_axi_rdata<=command_rx[127:96];
                16'h003c:s_axi_rdata<=32'h45434736; // ECG6: SW0 dual-path view
                16'h0040:s_axi_rdata<={31'd0,sw_stable};
                16'h001c:s_axi_rdata<={29'd0,frame_pending,frame_request,frame_ack_sync};
                default:s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule

