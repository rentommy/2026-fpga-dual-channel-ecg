// SPI mode 1, MSB first within each byte; byte 0 occupies tx[7:0].
// Extra setup/hold/gap periods conservatively satisfy ADS1292 CS timing.
module ads_spi_engine #(
    parameter integer CS_WAIT = 1000
)(
    input wire clk, resetn, start,
    input wire [127:0] tx,
    input wire [4:0] length,
    input wire [15:0] half_period,
    input wire miso,
    output reg busy, done,
    output reg [127:0] rx,
    output reg cs_n, sclk, mosi
);
    localparam IDLE=0, SETUP=1, SHIFT=2, HOLD_CS=3, GAP=4;
    reg [2:0] state;
    reg [15:0] timer, divider;
    reg [127:0] tx_latched;
    reg [4:0] bytes, byte_index;
    reg [2:0] bit_index;
    always @(posedge clk) begin
        if (!resetn) begin
            state<=IDLE; busy<=0; done<=0; rx<=0;
            cs_n<=1; sclk<=0; mosi<=0; timer<=0; divider<=89;
            bytes<=0; byte_index<=0; bit_index<=0; tx_latched<=0;
        end else begin
            done<=0;
            case (state)
            IDLE: begin
                busy<=0; cs_n<=1; sclk<=0; mosi<=0;
                if (start && length>=1 && length<=16) begin
                    tx_latched<=tx; bytes<=length; byte_index<=0; bit_index<=0;
                    divider<=(half_period<4)?4:half_period;
                    rx<=0; busy<=1; cs_n<=0; timer<=CS_WAIT-1; state<=SETUP;
                end
            end
            SETUP: if(timer==0) begin timer<=divider-1; state<=SHIFT; end
                   else timer<=timer-1;
            SHIFT: if(timer==0) begin
                timer<=divider-1;
                if(!sclk) begin
                    sclk<=1;
                    mosi<=tx_latched[byte_index*8+7-bit_index];
                end else begin
                    sclk<=0;
                    rx[byte_index*8+7-bit_index]<=miso;
                    if(bit_index==7) begin
                        bit_index<=0;
                        if(byte_index+1==bytes) begin timer<=CS_WAIT-1; state<=HOLD_CS; end
                        else byte_index<=byte_index+1;
                    end else bit_index<=bit_index+1;
                end
            end else timer<=timer-1;
            HOLD_CS: if(timer==0) begin cs_n<=1; timer<=CS_WAIT-1; state<=GAP; end
                     else timer<=timer-1;
            GAP: if(timer==0) begin busy<=0; done<=1; state<=IDLE; end
                 else timer<=timer-1;
            default: state<=IDLE;
            endcase
        end
    end
endmodule
