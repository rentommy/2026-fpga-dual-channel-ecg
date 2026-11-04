"""Encode movable 16-pixel glyphs for ECG4's per-column local pixel phase."""
import numpy as np
_GLYPHS=(np.arange(16,dtype=np.uint32)[None,:]<<8)|np.arange(128,dtype=np.uint32)[:,None]

def put_label(plane,column,text):
    """Write to the last axis, preserving phase when clipped at either edge."""
    width=plane.shape[-1]
    for index,char in enumerate(text):
        origin=int(column)+index*16
        left,right=max(0,origin),min(width,origin+16)
        if left<right:
            plane[...,left:right]=_GLYPHS[ord(char),left-origin:right-origin]
