function automatic [15:0] title_diag_live(input integer index);
begin
title_diag_live=16'h0020;
case(index)
0:title_diag_live=16'h5fc3;
1:title_diag_live=16'h7535;
2:title_diag_live=16'h6ce2;
3:title_diag_live=16'h5f62;
6:title_diag_live=16'h901a;
7:title_diag_live=16'h9053;
8:title_diag_live=16'h0031;
11:title_diag_live=16'h4fdd;
12:title_diag_live=16'h771f;
15:title_diag_live=16'h5b9e;
16:title_diag_live=16'h65f6;
19:title_diag_live=16'h81ea;
20:title_diag_live=16'h52a8;
21:title_diag_live=16'h589e;
22:title_diag_live=16'h76ca;
endcase
end
endfunction

function automatic [15:0] title_fast_hold(input integer index);
begin
title_fast_hold=16'h0020;
case(index)
0:title_fast_hold=16'h5fc3;
1:title_fast_hold=16'h7535;
2:title_fast_hold=16'h6ce2;
3:title_fast_hold=16'h5f62;
6:title_fast_hold=16'h901a;
7:title_fast_hold=16'h9053;
8:title_fast_hold=16'h0032;
11:title_fast_hold=16'h5feb;
12:title_fast_hold=16'h901f;
15:title_fast_hold=16'h51bb;
16:title_fast_hold=16'h7ed3;
19:title_fast_hold=16'h81ea;
20:title_fast_hold=16'h52a8;
21:title_fast_hold=16'h589e;
22:title_fast_hold=16'h76ca;
endcase
end
endfunction

function automatic [15:0] subtitle_demo(input integer index);
begin
subtitle_demo=16'h0020;
case(index)
0:subtitle_demo=16'h6f14;
1:subtitle_demo=16'h793a;
2:subtitle_demo=16'h6ce2;
3:subtitle_demo=16'h5f62;
5:subtitle_demo=16'h002f;
7:subtitle_demo=16'h0035;
8:subtitle_demo=16'h0030;
9:subtitle_demo=16'h0030;
10:subtitle_demo=16'h70b9;
11:subtitle_demo=16'h6bcf;
12:subtitle_demo=16'h79d2;
14:subtitle_demo=16'h002f;
16:subtitle_demo=16'h0034;
17:subtitle_demo=16'h79d2;
18:subtitle_demo=16'h7a97;
19:subtitle_demo=16'h53e3;
endcase
end
endfunction

function automatic [15:0] subtitle_adc(input integer index);
begin
subtitle_adc=16'h0020;
case(index)
0:subtitle_adc=16'h91c7;
1:subtitle_adc=16'h96c6;
2:subtitle_adc=16'h4fe1;
3:subtitle_adc=16'h53f7;
5:subtitle_adc=16'h002f;
7:subtitle_adc=16'h0035;
8:subtitle_adc=16'h0030;
9:subtitle_adc=16'h0030;
10:subtitle_adc=16'h70b9;
11:subtitle_adc=16'h6bcf;
12:subtitle_adc=16'h79d2;
14:subtitle_adc=16'h002f;
16:subtitle_adc=16'h0034;
17:subtitle_adc=16'h79d2;
18:subtitle_adc=16'h7a97;
19:subtitle_adc=16'h53e3;
endcase
end
endfunction

function automatic [15:0] subtitle_test(input integer index);
begin
subtitle_test=16'h0020;
case(index)
0:subtitle_test=16'h5185;
1:subtitle_test=16'h90e8;
2:subtitle_test=16'h6d4b;
3:subtitle_test=16'h8bd5;
4:subtitle_test=16'h4fe1;
5:subtitle_test=16'h53f7;
7:subtitle_test=16'h002f;
9:subtitle_test=16'h0035;
10:subtitle_test=16'h0030;
11:subtitle_test=16'h0030;
12:subtitle_test=16'h70b9;
13:subtitle_test=16'h6bcf;
14:subtitle_test=16'h79d2;
16:subtitle_test=16'h002f;
18:subtitle_test=16'h0034;
19:subtitle_test=16'h79d2;
20:subtitle_test=16'h7a97;
21:subtitle_test=16'h53e3;
endcase
end
endfunction

function automatic [15:0] subtitle_error(input integer index);
begin
subtitle_error=16'h0020;
case(index)
0:subtitle_error=16'h65e0;
1:subtitle_error=16'h91c7;
2:subtitle_error=16'h96c6;
3:subtitle_error=16'h6570;
4:subtitle_error=16'h636e;
6:subtitle_error=16'h002f;
8:subtitle_error=16'h8bf7;
9:subtitle_error=16'h68c0;
10:subtitle_error=16'h67e5;
11:subtitle_error=16'h8fde;
12:subtitle_error=16'h63a5;
endcase
end
endfunction

function automatic [15:0] footer(input integer index);
begin
footer=16'h0020;
case(index)
0:footer=16'h952e;
1:footer=16'h0030;
2:footer=16'h901a;
3:footer=16'h9053;
4:footer=16'h0031;
7:footer=16'h952e;
8:footer=16'h0031;
9:footer=16'h901a;
10:footer=16'h9053;
11:footer=16'h0032;
14:footer=16'h952e;
15:footer=16'h0032;
16:footer=16'h6a21;
17:footer=16'h5f0f;
20:footer=16'h952e;
21:footer=16'h0033;
22:footer=16'h51bb;
23:footer=16'h7ed3;
endcase
end
endfunction

function automatic [15:0] model_hint(input integer index);
begin
model_hint=16'h0020;
case(index)
0:model_hint=16'h9010;
1:model_hint=16'h62cd;
2:model_hint=16'h8bc6;
3:model_hint=16'h522b;
4:model_hint=16'hff1a;
5:model_hint=16'h5ef6;
6:model_hint=16'h540e;
7:model_hint=16'h56de;
8:model_hint=16'h586b;
12:model_hint=16'h95ee;
13:model_hint=16'h53f7;
14:model_hint=16'h8868;
15:model_hint=16'h793a;
16:model_hint=16'h7b49;
17:model_hint=16'h5f85;
endcase
end
endfunction
function automatic [15:0] heading(input integer index,input [2:0] sel);
begin
heading=title_diag_live(index);
case(index)
8:heading=sel[0]?16'h0032:16'h0031;
11:heading=sel[1]?16'h5feb:16'h4fdd;
12:heading=sel[1]?16'h901f:16'h771f;
15:heading=sel[2]?16'h51bb:16'h5b9e;
16:heading=sel[2]?16'h7ed3:16'h65f6;
endcase
end
endfunction
function automatic [15:0] subtitle(input integer index,input [1:0] flags);
begin
if(flags==3) subtitle=subtitle_test(index);
else if(flags[0]) subtitle=subtitle_demo(index);
else if(flags[1]) subtitle=subtitle_error(index);
else subtitle=subtitle_adc(index);
end
endfunction
