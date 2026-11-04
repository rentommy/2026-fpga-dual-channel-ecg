// FP32 Conv1d engine for experiment_09: ARM retains GroupNorm/RR/control.
// Eight adjacent output positions; eight partial sums hide FP adder latency.
extern "C" void ecg_conv(const float *input, const float *weights,
                          const float *bias, float *output,
                          int cin, int cout, int kernel, int dilation) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem0 depth=26240
#pragma HLS INTERFACE m_axi port=weights offset=slave bundle=gmem0 depth=81920
#pragma HLS INTERFACE m_axi port=bias offset=slave bundle=gmem0 depth=128
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem1 depth=26240
#pragma HLS INTERFACE s_axilite port=input bundle=ctrl offset=0x10
#pragma HLS INTERFACE s_axilite port=weights bundle=ctrl offset=0x1c
#pragma HLS INTERFACE s_axilite port=bias bundle=ctrl offset=0x28
#pragma HLS INTERFACE s_axilite port=output bundle=ctrl offset=0x34
#pragma HLS INTERFACE s_axilite port=cin bundle=ctrl offset=0x40
#pragma HLS INTERFACE s_axilite port=cout bundle=ctrl offset=0x48
#pragma HLS INTERFACE s_axilite port=kernel bundle=ctrl offset=0x50
#pragma HLS INTERFACE s_axilite port=dilation bundle=ctrl offset=0x58
#pragma HLS INTERFACE s_axilite port=return bundle=ctrl
    if(cin<1 || cin>128 || cout<1 || cout>128 ||
       !(kernel==1 || kernel==5 || kernel==15 || kernel==31) ||
       dilation<1 || dilation>4 || (kernel>5 && cin!=2)) return;
    const int N=205;
    float x[128][208];
#pragma HLS ARRAY_PARTITION variable=x cyclic factor=8 dim=2
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=bram
    float w[3968];
#pragma HLS BIND_STORAGE variable=w type=ram_2p impl=bram
    for(int c=0;c<cin;c++) {
        for(int t=0;t<N;t++) {
#pragma HLS PIPELINE II=1
            x[c][t]=input[c*N+t];
        }
    }
    for(int oc=0;oc<cout;oc++) {
        for(int j=0;j<cin*kernel;j++) {
#pragma HLS PIPELINE II=1
            w[j]=weights[oc*cin*kernel+j];
        }
        float b=bias[oc];
        for(int t0=0;t0<N;t0+=8) {
            float partial[8][8];
#pragma HLS ARRAY_PARTITION variable=partial complete dim=0
            for(int r=0;r<8;r++) {
#pragma HLS UNROLL
                for(int lane=0;lane<8;lane++) {
#pragma HLS UNROLL
                    partial[r][lane]=0;
                }
            }
            int c=0,k=0;
            dot: for(int j=0;j<cin*kernel;j++) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=partial type=inter direction=RAW distance=8 true
                const float weight=w[j];
                const int base=t0+k*dilation-((kernel-1)*dilation)/2;
                const int r=j&7;
                for(int lane=0;lane<8;lane++) {
#pragma HLS UNROLL
                    int t=base+lane;
                    float v=(t>=0 && t<N)?x[c][t]:0.0f;
                    partial[r][lane]=partial[r][lane]+v*weight;
                }
                if(k==kernel-1) {k=0;c++;} else k++;
            }
            for(int lane=0;lane<8;lane++) {
#pragma HLS PIPELINE II=1
                float a0=partial[0][lane]+partial[1][lane];
                float a1=partial[2][lane]+partial[3][lane];
                float a2=partial[4][lane]+partial[5][lane];
                float a3=partial[6][lane]+partial[7][lane];
                if(t0+lane<N) output[oc*N+t0+lane]=((a0+a1)+(a2+a3))+b;
            }
        }
    }
}
