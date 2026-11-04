`timescale 1ns/1ps
module tb_ecg_io;
 reg clk=0,pclk=0,rstn=0;always #5 clk=~clk;always #20 pclk=~pclk;
 reg [15:0] aw=0,ar=0;reg av=0,wv=0,br=1,rv=0,rr=0;
 wire awr,wr,bv,arr,rdv;wire [1:0] bp,rp;reg [31:0] wd=0;reg [3:0] ws=15;wire[31:0] rd;
 reg miso=0,drdy=1,sw0=0;wire cs,sc,mo,st,pw;reg[3:0]btn=0;
 wire[23:0]rgb;wire hs,vs,de;
 ecg_io_top #(.FIFO_AW(2),.DEBOUNCE_CYCLES(4),.SPI_CS_WAIT(4)) dut(
 .s_axi_aclk(clk),.s_axi_aresetn(rstn),.s_axi_awaddr(aw),.s_axi_awprot(3'd0),.s_axi_awvalid(av),.s_axi_awready(awr),
 .s_axi_wdata(wd),.s_axi_wstrb(ws),.s_axi_wvalid(wv),.s_axi_wready(wr),.s_axi_bresp(bp),.s_axi_bvalid(bv),.s_axi_bready(br),
 .s_axi_araddr(ar),.s_axi_arprot(3'd0),.s_axi_arvalid(rv),.s_axi_arready(arr),.s_axi_rdata(rd),.s_axi_rresp(rp),.s_axi_rvalid(rdv),.s_axi_rready(rr),
 .ads_dout(miso),.ads_drdy_n(drdy),.ads_cs_n(cs),.ads_sclk(sc),.ads_din(mo),.ads_start(st),.ads_pwdn_reset_n(pw),.buttons(btn),
 .pixel_clk(pclk),.pixel_resetn(rstn),.sw0(sw0),.hdmi_hpd(1'b1),.video_rgb(rgb),.video_hsync(hs),.video_vsync(vs),.video_de(de));
 task automatic addr_write(input[15:0]a);
 begin @(negedge clk);aw=a;av=1;do @(posedge clk);while(!awr);@(negedge clk);av=0;end endtask
 task automatic data_write(input[31:0]d);
 begin @(negedge clk);wd=d;wv=1;do @(posedge clk);while(!wr);@(negedge clk);wv=0;end endtask
 task automatic write_reg(input[15:0]a,input[31:0]d,input bit data_first);
 begin
  if(data_first)begin data_write(d);repeat(2)@(posedge clk);addr_write(a);end
  else begin addr_write(a);repeat(2)@(posedge clk);data_write(d);end
  do @(posedge clk);while(!bv);if(bp!=0)$fatal(1,"AXI write failed %h",a);@(negedge clk);
 end endtask
 task automatic read_reg(input[15:0]a,output[31:0]d);
 reg[31:0]hold;
 begin
  @(negedge clk);ar=a;rv=1;rr=0;do @(posedge clk);while(!arr);@(negedge clk);rv=0;
  while(!rdv)@(negedge clk);hold=rd;if(rp!=0)$fatal(1,"AXI read failed %h",a);
  repeat(3)begin @(negedge clk);if(rd!=hold || !rdv)$fatal(1,"RDATA unstable under backpressure");end
  d=hold;rr=1;@(posedge clk);@(negedge clk);rr=0;
 end endtask
 reg[127:0]response=0,received=0;integer bitnumber=0;
 always @(negedge cs)begin bitnumber=0;received=0;end
 always @(posedge sc)begin
  if(cs)$fatal(1,"SCLK while deselected");
  miso=response[(bitnumber/8)*8+7-(bitnumber%8)];
 end
 always @(negedge sc)if(!cs)begin
  received[(bitnumber/8)*8+7-(bitnumber%8)]=mo;bitnumber=bitnumber+1;
 end
 task automatic pulse_drdy;
 begin @(negedge clk);drdy=0;repeat(4)@(negedge clk);drdy=1;repeat(750)@(negedge clk);end endtask
 reg[31:0]value;integer i;
 initial begin
  #100;@(negedge clk);rstn=1;repeat(5)@(posedge clk);
  if(!cs || sc || st || !pw)$fatal(1,"unsafe reset pins");
  read_reg(16'h3c,value);if(value!=32'h45434736)$fatal(1,"ABI");
  sw0=1;repeat(2)@(negedge clk);sw0=0;repeat(12)@(negedge clk);
  read_reg(16'h40,value);if(value!=0)$fatal(1,"SW0 bounce not rejected");
  sw0=1;repeat(12)@(negedge clk);read_reg(16'h40,value);if(value!=1)$fatal(1,"SW0 high");
  sw0=0;repeat(12)@(negedge clk);read_reg(16'h40,value);if(value!=0)$fatal(1,"SW0 low");
  write_reg(12,4,1);write_reg(16'h100,32'h00a55a11,0);
  response=128'h332211;write_reg(8,3,1);repeat(250)@(posedge clk);
  read_reg(4,value);if(!value[1]||value[0])$fatal(1,"manual command did not complete");
  read_reg(16'h200,value);if(value[23:0]!=24'h332211)$fatal(1,"SPI receive byte/bit order %h",value);
  if(received[23:0]!=24'ha55a11)$fatal(1,"SPI transmit byte/bit order");
  response=128'h563412feffff0000c0;
  write_reg(0,15,0); // clear FIFO and enable automatic reads/start/reset release
  pulse_drdy();read_reg(4,value);if(value[26:16]!=1)$fatal(1,"FIFO push %h",value);
  read_reg(32,value);if(value!=32'hc00000)$fatal(1,"status byte order");
  read_reg(36,value);if(value!=32'hfffffffe)$fatal(1,"CH1 sign extension %h",value);
  read_reg(40,value);if(value!=32'h00123456)$fatal(1,"CH2 sign extension %h",value);
  read_reg(4,value);if(value[26:16]!=0)$fatal(1,"FIFO pop handshake");
  for(i=0;i<5;i=i+1)pulse_drdy();
  read_reg(4,value);if(value[26:16]!=4)$fatal(1,"FIFO bound");
  read_reg(48,value);if(value!=1)$fatal(1,"lost DRDY not counted %d",value);
  write_reg(0,15,0);response=0;pulse_drdy();
  read_reg(52,value);if(value!=1)$fatal(1,"invalid status not counted");
  btn=2;repeat(12)@(posedge clk);btn=0;repeat(12)@(posedge clk);
  read_reg(16,value);if(value[0]!=1)$fatal(1,"channel2 button");
  btn=4;repeat(20)@(posedge clk);btn=0;repeat(12)@(posedge clk);
  read_reg(16,value);if(value[2:0]!=3)$fatal(1,"path toggle / debounce");
  write_reg(16'h4000,{12'd0,10'd280,10'd240},1);
  write_reg(16'h7000,32'd78,1);
  write_reg(16'ha000,32'h0003a55a,0);
  write_reg(16'haa00-4,32'h0001ffff,1);
  if(dut.video.hud_mem1[0]!=18'h3a55a || dut.video.hud_mem1[639]!=18'h1ffff)$fatal(1,"HUD address range failed");
  write_reg(16'h97fc,32'd86,0);
  if(dut.video.label_mem1[0]!=78 || dut.video.label_mem1[2559]!=86)$fatal(1,"label address window failed");
  write_reg(16'h1c,1,0);
  read_reg(16'h1c,value);if(value!=6)$fatal(1,"frame commit pending status %h",value);
  addr_write(16'h4000);data_write(32'd0);
  do @(posedge clk);while(!bv);
  if(bp!=2)$fatal(1,"pending buffer write was not rejected");
  @(negedge clk);
  if(dut.video.wave_mem1[0]!={10'd280,10'd240})$fatal(1,"pending frame memory changed");
  addr_write(16'h7000);data_write(32'd0);
  do @(posedge clk);while(!bv);
  if(bp!=2)$fatal(1,"pending label write was not rejected");
  @(negedge clk);
  if(dut.video.label_mem1[0]!=78)$fatal(1,"pending label memory changed");
  addr_write(16'ha000);data_write(32'd0);
  do @(posedge clk);while(!bv);
  if(bp!=2)$fatal(1,"pending HUD write accepted");
  @(negedge clk);
  if(dut.video.hud_mem1[0]!=18'h3a55a)$fatal(1,"pending HUD changed");
  write_reg(16'h14,0,0);read_reg(16,value);if(value[2:0]!=0)$fatal(1,"software UI control");
  $display("ECG_IO_RTL_PASS: decoupled AXI, backpressure, mode1 SPI, FIFO, sign extension, overflow, invalid frames, buttons");
  $finish;
 end
 initial begin #2000000;$fatal(1,"simulation timeout");end
endmodule
