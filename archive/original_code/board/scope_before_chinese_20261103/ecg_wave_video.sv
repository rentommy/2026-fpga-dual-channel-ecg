// 640x480 at 60 Hz with a 25.2-MHz pixel clock. BRAM holds four waveform banks:
// bank = channel*2+path, each column packs {y_max[9:0], y_min[9:0]}.
module ecg_wave_video(
    input wire bus_clk, wave_we,
    input wire [11:0] wave_addr,
    input wire [19:0] wave_data,
    input wire wave_write_bank, frame_request,
    output reg frame_active,
    input wire pixel_clk, pixel_resetn,
    input wire [2:0] selection,
    input wire [1:0] display_flags,
    output reg [23:0] rgb,
    output reg hsync, vsync, de
);
    (* ram_style="block" *) reg [19:0] wave_mem0 [0:2559];
    (* ram_style="block" *) reg [19:0] wave_mem1 [0:2559];
    integer k;
    initial for(k=0;k<2560;k=k+1) begin
        wave_mem0[k]={10'd260,10'd260};
        wave_mem1[k]={10'd260,10'd260};
    end
    always @(posedge bus_clk) if(wave_we && wave_addr<2560) begin
        if(wave_write_bank) wave_mem1[wave_addr]<=wave_data;
        else wave_mem0[wave_addr]<=wave_data;
    end
    (* ASYNC_REG="TRUE" *) reg request_meta, request_sync;
    (* ASYNC_REG="TRUE" *) reg [4:0] ui_meta, ui_sync;
    reg [4:0] ui_frame;
    reg [9:0] hx, vy, x1, y1;
    reg hs1, vs1, de1;
    reg [19:0] column0, column1;
    wire [19:0] column=frame_active?column1:column0;
    wire [11:0] bank_base = (ui_frame[0] ? 12'd1280 : 12'd0) + (ui_frame[1] ? 12'd640 : 12'd0);
    wire [11:0] ram_addr = bank_base + ((hx<640)?hx:10'd0);
    wire [9:0] lo=column[9:0], hi=column[19:10];
    reg [23:0] color;
    reg [7:0] character, bits_row;
    integer ci, cr, cc;
    `include "ecg_font.vh"
    function automatic [7:0] heading(input integer index, input [2:0] sel);
        begin
            heading=" ";
            case(index)
             0:heading="E";1:heading="C";2:heading="G";
             4:heading="C";5:heading="H";6:heading=sel[0]?"2":"1";
             9:heading=sel[1]?"F":"D";10:heading=sel[1]?"A":"I";
             11:heading=sel[1]?"S":"A";12:heading=sel[1]?"T":"G";
             15:heading=sel[2]?"H":"L";16:heading=sel[2]?"O":"I";
             17:heading=sel[2]?"L":"V";18:heading=sel[2]?"D":"E";
             21:heading="A";22:heading="U";23:heading="T";24:heading="O";
            endcase
        end
    endfunction
    function automatic [7:0] subtitle(input integer index, input [1:0] flags);
        reg [255:0] line;
        begin
            if(flags[0]) line="DEMO WAVEFORM / 500 SPS / 4 SEC ";
            else if(flags[1]) line="NO ADC DATA / CHECK CONNECTION  ";
            else line="ADC WAVEFORM / 500 SPS / 4 SEC  ";
            subtitle=(index>=0 && index<32)?line[(31-index)*8+:8]:8'h20;
        end
    endfunction
    function automatic [7:0] footer(input integer index);
        reg [383:0] line;
        begin
            line="BTN0 CH1  BTN1 CH2  BTN2 PATH  BTN3 HOLD        ";
            footer=(index>=0 && index<48)?line[(47-index)*8+:8]:8'h20;
        end
    endfunction
    always @* begin
        color=24'h070d17;
        character=" "; bits_row=0;ci=0;cr=0;cc=0;
        if(y1>=80 && y1<440) begin
            if(x1%80==0 || (y1-80)%40==0) color=24'h233447;
            if(y1==260) color=24'h40526a;
            if(y1>=lo && y1<=hi) color=ui_frame[0]?24'h30d5ff:24'h43f296;
        end
        if(x1>=16 && x1<624 && y1>=16 && y1<32) begin
            ci=(x1-16)>>4; cr=(y1-16)>>1;cc=((x1-16)>>1)&7;
            character=heading(ci,ui_frame[2:0]);bits_row=font_row(character,cr[2:0]);
            if(bits_row[7-cc]) color=24'heaf2ff;
        end
        if(x1>=16 && x1<528 && y1>=44 && y1<60) begin
            ci=(x1-16)>>4; cr=(y1-44)>>1;cc=((x1-16)>>1)&7;
            character=subtitle(ci,ui_frame[4:3]);bits_row=font_row(character,cr[2:0]);
            if(bits_row[7-cc]) color=ui_frame[3]?24'hffd166:24'h90b5dc;
        end
        if(x1>=16 && x1<400 && y1>=460 && y1<468) begin
            ci=(x1-16)>>3; cr=y1-460;cc=(x1-16)&7;
            character=footer(ci);bits_row=font_row(character,cr[2:0]);
            if(bits_row[7-cc]) color=24'h90b5dc;
        end
    end
    always @(posedge pixel_clk) begin
        ui_meta<={display_flags,selection};ui_sync<=ui_meta;
        request_meta<=frame_request;request_sync<=request_meta;
        column0<=wave_mem0[ram_addr];
        column1<=wave_mem1[ram_addr];
        if(!pixel_resetn) begin
            hx<=0;vy<=0;x1<=0;y1<=0;hs1<=1;vs1<=1;de1<=0;
            rgb<=0;hsync<=1;vsync<=1;de<=0;
            ui_meta<=0;ui_sync<=0;ui_frame<=0;
            request_meta<=0;request_sync<=0;frame_active<=0;
        end else begin
            // Change the displayed buffer and UI only after active video ends.
            // The acknowledged buffer remains read-only for the entire frame.
            if(hx==0 && vy==480) begin
                frame_active<=request_sync;
                ui_frame<=ui_sync;
            end
            if(hx==799) begin hx<=0;vy<=(vy==524)?0:vy+1;end else hx<=hx+1;
            x1<=hx;y1<=vy;
            hs1<=!(hx>=656 && hx<752);vs1<=!(vy>=490 && vy<492);
            de1<=(hx<640 && vy<480);
            rgb<=de1?color:24'd0;hsync<=hs1;vsync<=vs1;de<=de1;
        end
    end
endmodule
