"""Seven-output, validation-only controlled pilot; never evaluates old test."""
from pathlib import Path
import json,hashlib,csv,time,shutil,random
import numpy as np
import torch
from torch import nn
from sklearn.metrics import classification_report,confusion_matrix,f1_score
from models import BeatModel
ROOT=Path(__file__).resolve().parent
CLASSES=['A','F','L','N','R','V','|']
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    torch.set_num_threads(8)
    out=ROOT/'runs';out.mkdir(exist_ok=False)
    source=ROOT.parent/'benchmark_03/data/beats.npz'
    d=np.load(source);old=['A','B','F','L','N','R','S','V','|'];lookup=np.array([CLASSES.index(c) if c in CLASSES else -1 for c in old]);labels=lookup[d['labels']]
    tr=np.flatnonzero((d['split']==0)&(labels>=0));va=np.flatnonzero((d['split']==1)&(labels>=0))
    assert not(set(d['record'][tr])&set(d['record'][va]))
    mean=d['rr'][tr].mean(0);std=d['rr'][tr].std(0)+1e-6
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    arrays={s:(torch.tensor(d['warped'][ix],device=device),torch.tensor(np.clip((d['rr'][ix]-mean)/std,-8,8),device=device),torch.tensor(labels[ix],device=device)) for s,ix in [('train',tr),('val',va)]}
    counts=np.bincount(labels[tr],minlength=7);w=np.clip(np.sqrt(counts.max()/counts),1,12);w/=w.mean()
    protocol={'classes':CLASSES,'excluded':['B','S'],'input':'frozen midpoint central beat; warped 108/180; same RR branch for all models','source_sha256':sha(source),'models':['cnn','gru','se_gru'],'seed':0,'epochs':25,'patience':6,'lr':.001,'batch':256,'weights':w.tolist(),'rr_mean':mean.tolist(),'rr_std':std.tolist(),'train_count':len(tr),'val_count':len(va),'selection':'validation supported macro F1','test':'not evaluated; old test already consumed; independent final validation still required','purpose':'controlled architecture pilot, not exact source reproduction or demonstrated stable improvement'}
    save(ROOT/'protocol.json',protocol)
    shutil.copy2(__file__,out/'run_snapshot.py');shutil.copy2(ROOT/'models.py',out/'model_snapshot.py')
    loss_fn=nn.CrossEntropyLoss(weight=torch.tensor(w,dtype=torch.float32,device=device));results={}
    for kind in protocol['models']:
        torch.manual_seed(0);random.seed(0);np.random.seed(0)
        folder=out/kind;folder.mkdir();model=BeatModel(kind).to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
        save(folder/'config.json',{'kind':kind,'classes':CLASSES,'parameters':sum(p.numel() for p in model.parameters()),'protocol_sha256':sha(ROOT/'protocol.json'),'code_sha256':sha(out/'run_snapshot.py'),'model_sha256':sha(out/'model_snapshot.py')})
        best=-1;wait=0;history=[]
        for epoch in range(1,26):
            start=time.time();model.train();x,r,y=arrays['train'];order=torch.randperm(len(y),device=device);loss_total=0
            for batch in order.split(256):
                optimizer.zero_grad(set_to_none=True);loss=loss_fn(model(x[batch],r[batch]),y[batch]);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step();loss_total+=loss.item()*len(batch)
            model.eval();x,r,y=arrays['val'];pred=[]
            with torch.no_grad():
                for j in range(0,len(y),256):pred.extend(model(x[j:j+256],r[j:j+256]).argmax(1).cpu().tolist())
            truth=y.cpu().numpy();score=float(f1_score(truth,pred,labels=list(range(7)),average='macro',zero_division=0))
            history.append({'epoch':epoch,'train_loss':loss_total/len(tr),'val_macro_f1':score,'seconds':time.time()-start});save(folder/'history.json',history)
            print(kind,history[-1],flush=True)
            if score>best:
                best=score;wait=0;torch.save(model.state_dict(),folder/'best.pt');np.save(folder/'val_predictions.npy',pred)
                save(folder/'val_metrics.json',{'epoch':epoch,'macro_f1':score,'accuracy':float(np.mean(truth==pred)),'report':classification_report(truth,pred,labels=list(range(7)),target_names=CLASSES,output_dict=True,zero_division=0),'confusion_matrix':confusion_matrix(truth,pred,labels=list(range(7))).tolist()})
            else:wait+=1
            if wait>=6:break
        results[kind]=json.loads((folder/'val_metrics.json').read_text())
    save(ROOT/'results.json',results)
    lines=['# 参考项目结构改编：七输出验证结果','','同一逐拍输入、同一训练/验证受试者、同一 RR 分支、权重和训练预算。B/S 已从目标及输出移除。仅一个随机种子，不能据此证明稳定提升。未重新评估旧测试集。','','| 模型 | 验证准确率 | 验证 macro-F1 | A 精确率 | A 召回率 | L 召回率 | R 召回率 |','|---|---:|---:|---:|---:|---:|---:|']
    for k,v in results.items():
        r=v['report'];lines.append(f'| {k} | {v["accuracy"]:.2%} | {v["macro_f1"]:.4f} | {r["A"]["precision"]:.2%} | {r["A"]["recall"]:.2%} | {r["L"]["recall"]:.2%} | {r["R"]["recall"]:.2%} |')
    lines+=['','模型为结构思路改编，不能称为原 TensorFlow 项目的等价复现。此前九输出实验与这里的七输出实验也不是仅改变结构的严格对照；严格对照限于本表三行。']
    (ROOT/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':main()
