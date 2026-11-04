`timescale 1ns/1ps
module tb_dual_view;
reg busclk=0,pclk=0,resetn=0,dual=0;
always #5 busclk=~busclk;always #20 pclk=~pclk;
wire[23:0]rgb;wire hs,vs,de,active;
ecg_wave_video dut(.bus_clk(busclk),.wave_we(1'b0),.label_we(1'b0),.hud_we(1'b0),.wave_addr(12'd0),.wave_data(20'd0),
 .wave_write_bank(1'b1),.frame_request(1'b0),.frame_active(active),.pixel_clk(pclk),.pixel_resetn(resetn),
 .selection(3'b010),.dual_view(dual),.display_flags(2'b01),.rgb(rgb),.hsync(hs),.vsync(vs),.de(de));
integer x,fd,pixels,top_hits,bottom_hits;
initial begin
 #1;
 for(x=0;x<640;x=x+1)begin
 dut.wave_mem0[x]={10'd301,10'd299};
 dut.wave_mem0[640+x]={10'd201,10'd199};
 end
 #100;resetn=1;
 wait(dut.hx==200 && dut.vy==200);dual=1;
 repeat(10)@(posedge pclk);
 if(dut.ui_frame[5])$fatal(1,"SW0 changed during active frame");
 wait(dut.ui_frame[5]);wait(dut.hx==0 && dut.vy==0);
 fd=$fopen("dual_view.ppm","wb");$fwrite(fd,"P6\n640 480\n255\n");
 pixels=0;top_hits=0;bottom_hits=0;
 while(pixels<640*480)begin
 @(posedge pclk);#1;
 if(de)begin
 if(pixels%640==300 && pixels/640==140 && rgb==24'h43f296)top_hits=top_hits+1;
 if(pixels%640==300 && pixels/640==370 && rgb==24'h43f296)bottom_hits=bottom_hits+1;
 $fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);pixels=pixels+1;
 end
 end
 $fclose(fd);
 if(top_hits!=1 || bottom_hits!=1)$fatal(1,"wrong dual path banks/mapping %d %d",top_hits,bottom_hits);
 dual=0;wait(!dut.ui_frame[5]);wait(dut.hx==300 && dut.vy==200);repeat(2)@(posedge pclk);#1;
 if(rgb!=24'h43f296)$fatal(1,"single FAST view did not return");
 $display("DUAL_VIEW_PASS: independent FAST/DIAG banks, split mapping, vertical-blank switching and single-view return");$finish;
end
initial begin #100000000;$fatal(1,"timeout");end
endmodule
