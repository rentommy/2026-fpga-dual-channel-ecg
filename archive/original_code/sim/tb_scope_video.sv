`timescale 1ns/1ps
module tb_scope_video;
reg busclk=0,pclk=0,resetn=0,we=0,label_we=0,hud_we=0;
always #5 busclk=~busclk;always #20 pclk=~pclk;
reg[11:0]addr=0;reg[19:0]data=0;
wire[23:0]rgb;wire hs,vs,de;
reg[2:0]sel=0;
reg write_bank=1,request=0;
wire active_bank;
ecg_wave_video dut(.bus_clk(busclk),.wave_we(we),.label_we(label_we),.hud_we(hud_we),.wave_addr(addr),.wave_data(data),
 .wave_write_bank(write_bank),.frame_request(request),.frame_active(active_bank),
 .pixel_clk(pclk),.pixel_resetn(resetn),.selection(sel),.dual_view(1'b0),.display_flags(2'b01),
 .rgb(rgb),.hsync(hs),.vsync(vs),.de(de));
integer x,y,fd,pixels,last_hs=1,hs_edges=0,cyan_pixels=0,label_pixels=0;
reg [7:0] expected_row;
initial begin
 for(x=0;x<640;x=x+1)begin
  y=260+$rtoi(100*$sin(6.283185307*x/160));
  @(negedge busclk);we=1;addr=x;data={(10'(y+1)),(10'(y-1))};
 end
 for(x=37;x<53;x=x+1)begin
  @(negedge busclk);we=0;label_we=1;addr=x;data=((x-37)<<8)|78;
 end
 @(negedge busclk);label_we=0;hud_we=1;addr=50;data=18'h1a55a;
 @(negedge busclk);hud_we=0;resetn=1;
 if(dut.hud_mem1[50]!=18'h1a55a || dut.hud_mem0[50]!=0)$fatal(1,"HUD bank isolation failed");
 if(dut.label_mem1[37]!=78 || dut.label_mem1[52]!=12'hf4e || dut.label_mem0[37]!=0)$fatal(1,"label bank/phase isolation failed");
 repeat(5)@(posedge pclk);
 request=1;
 // Start the dump at a frame boundary after the reset/CDC pipeline has settled.
 @(negedge vs);@(posedge vs);
 wait(dut.hx==0 && dut.vy==0);
 fd=$fopen("scope_demo.ppm","wb");
 $fwrite(fd,"P6\n640 480\n255\n");pixels=0;
 while(pixels<640*480)begin
  @(posedge pclk);#1;
  if(de)begin
   if(pixels%640==50 && pixels/640>=64 && pixels/640<80)begin
    if((rgb==24'h56e3ba)!=((16'ha55a>>(15-(pixels/640-64)))&1))$fatal(1,"HUD pixel mismatch");
   end
   if(pixels/640>=84 && pixels/640<100 && pixels%640>=37 && pixels%640<53)begin
    expected_row=dut.font_row(8'd78,(pixels/640-84)/2);
    if(expected_row[7-((pixels%640-37)/2)] != (rgb==24'hffd166))$fatal(1,"unaligned label pixel mismatch at %d",pixels);
    if(rgb==24'hffd166)label_pixels=label_pixels+1;
   end
   $fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);pixels=pixels+1;
  end
  if(last_hs && !hs)hs_edges=hs_edges+1;
  last_hs=hs;
 end
 $fclose(fd);
 if(hs_edges<479 || hs_edges>480)$fatal(1,"unexpected horizontal sync count %d",hs_edges);
 if(active_bank!=1)$fatal(1,"first buffer was not committed");
 if(label_pixels<8)$fatal(1,"beat label glyph was not rendered");
 write_bank=0;
 for(x=0;x<640;x=x+1)begin
  y=160+(x%200);
  @(negedge busclk);we=1;addr=1920+x;data={(10'(y+1)),(10'(y-1))};
 end
 @(negedge busclk);we=0;label_we=1;addr=1952;data=86;
 @(negedge busclk);label_we=0;sel=7; // CH2, FAST, HOLD
 if(dut.label_mem0[1952]!=86 || dut.label_mem1[1952]!=0)$fatal(1,"second label bank isolation failed");
 request=0;
 wait(active_bank==0);
 wait(dut.hx==0 && dut.vy==0);
 fd=$fopen("scope_channel2.ppm","wb");$fwrite(fd,"P6\n640 480\n255\n");pixels=0;
 while(pixels<640*480)begin
  @(posedge pclk);#1;
  if(de)begin
   $fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);pixels=pixels+1;
   if(rgb==24'h30d5ff)cyan_pixels=cyan_pixels+1;
  end
 end
 $fclose(fd);
 if(cyan_pixels<640 || dut.ui_frame[2:0]!=7)$fatal(1,"channel/path display selection failed");
 $display("SCOPE_VIDEO_RTL_PASS: two 307200-pixel frames, sync, CH2 FAST HOLD bank selection");$finish;
end
reg previous_bank=0;
integer previous_hx=0,previous_vy=0;
always @(posedge pclk) begin
 #1;
 if(resetn && active_bank!=previous_bank && !(previous_hx==0 && previous_vy==480))
   $fatal(1,"buffer switched outside vertical blank");
 previous_bank=active_bank;previous_hx=dut.hx;previous_vy=dut.vy;
end
initial begin #100000000;$fatal(1,"video timeout");end
endmodule
