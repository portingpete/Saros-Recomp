"""Recover exact per-invocation addresses in the 256-thread filter's shared array."""
from collections import Counter
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
import json
import re
import os

root=Path(__file__).resolve().parent
asm=Path(os.environ['LDS_INPUT_ASM'])
u32=2**32-1
class Unknown(Exception):pass
def inspect():
    lines=asm.read_text().splitlines(); rows=[];defs={};lineof={};labels={}
    for line in lines:
        parsed=re.match(r'^\s*(?:(%\S+) = )?Op(\w+)\s*(.*)$',line)
        if not parsed:continue
        rid,op,tail=parsed.groups();args=tail.split();i=len(rows)
        if rid:defs[rid]=(op,args);lineof[rid]=i
        if op=='Label':labels[rid]=i
        rows.append((rid,op,args))
    assert any(op=='ExecutionMode' and a[1:]==['LocalSize','256','1','1'] for _,op,a in rows)
    assert sum(op=='Function' for _,op,_ in rows)==1
    assert not any(op in ('LoopMerge','Switch','FunctionCall','CopyMemory','CopyMemorySized','PtrAccessChain') for _,op,_ in rows)
    globals_=[rid for rid,(op,a) in defs.items() if op=='Variable' and a[-1]=='Workgroup']
    assert globals_==['%2631']
    shared=globals_[0]; length=5120
    assert defs[shared][1][0]=='%_ptr_Workgroup__arr_uint_uint_5120'
    assert defs['%_arr_uint_uint_5120']==('TypeArray',['%uint','%uint_5120'])
    assert defs['%uint_5120']==('Constant',['%uint','5120'])
    edges=[]; bars=[]; accesses=[]; unknown=Counter(); uses=Counter()
    for i,(rid,op,a) in enumerate(rows):
        if op=='ControlBarrier':
            assert a==['%uint_2','%uint_2','%uint_2376'];bars.append(i)
        if op in ('Branch','BranchConditional'):
            edges.extend((i,labels[x]) for x in (a[1:3] if op=='BranchConditional' else a[:1]))
        uses.update(x for x in a if x.startswith('%'))
    assert all(b>a for a,b in edges)
    @lru_cache(None)
    def val(name,mask):
        if not mask:return (0,)*256
        op,a=defs[name]
        def scalar(x):
            typ,v=defs[x]
            if typ!='Constant' or v[0]!='%uint':raise Unknown((name,op))
            return int(v[1])
        if op=='Constant' and a[0]=='%uint':return (int(a[1]) & mask,)*256
        if op=='Load' and a[1] in ('%109','%gl_LocalInvocationIndex'):
            assert defs['%109']==('AccessChain',['%_ptr_Input_uint','%gl_LocalInvocationID','%uint_0'])
            return tuple(x & mask for x in range(256))
        if op=='BitFieldUExtract':
            offset,n=map(scalar,a[-2:]);assert offset+n<=32
            q=(mask & ((1<<n)-1))<<offset
            return tuple(x>>offset for x in val(a[1],q))
        if op=='BitFieldInsert':
            off,n=map(scalar,a[-2:]);assert off+n<=32
            field=((1<<n)-1)<<off
            return tuple(x | (y<<off) for x,y in zip(val(a[1],mask&~field),val(a[2],(mask&field)>>off)))
        if op=='ShiftLeftLogical':
            count=scalar(a[2]);assert count<32
            return tuple(x<<count for x in val(a[1],mask>>count))
        if op=='ShiftRightLogical':
            count=scalar(a[2]);assert count<32
            return tuple(x>>count for x in val(a[1],(mask<<count)&u32))
        if op in ('IAdd','ISub','IMul'):
            needed=(1<<mask.bit_length())-1
            x=val(a[1],needed);y=val(a[2],needed)
            if op=='IAdd':return tuple((p+q)&mask for p,q in zip(x,y))
            if op=='ISub':return tuple((p-q)&mask for p,q in zip(x,y))
            return tuple((p*q)&mask for p,q in zip(x,y))
        if op=='BitwiseAnd':
            for j,k in [(1,2),(2,1)]:
                if defs[a[j]][0]=='Constant':return val(a[k],scalar(a[j])&mask)
            return tuple(x&y for x,y in zip(val(a[1],mask),val(a[2],mask)))
        if op in ('BitwiseOr','BitwiseXor'):
            x=val(a[1],mask);y=val(a[2],mask)
            if op=='BitwiseOr':return tuple(p|q for p,q in zip(x,y))
            return tuple(p^q for p,q in zip(x,y))
        if op=='CopyObject' and a[0]=='%uint':return val(a[1],mask)
        raise Unknown((name,op))
    roots={}
    for i,(rid,op,a) in enumerate(rows):
        if shared in a:assert op=='AccessChain' and a[:2]==['%_ptr_Workgroup_uint',shared] and len(a)==3
        if op=='AccessChain' and a[1]==shared:
            assert uses[rid]==1
            roots[rid]=(a[2],i)
        if op in ('Load','Store') and (ptr:=a[1 if op=='Load' else 0]) in roots:
            index,definition=roots[ptr];assert a[-1]=='None'
            try:words=val(index,u32)
            except Unknown as e:unknown[str(e)]+=1;words=None
            accesses.append(dict(line=i,definition=definition,index=index,op=op,words=words))
    assert len(accesses)==len(roots)
    return rows,defs,edges,bars,accesses,unknown
if __name__=='__main__':
    rows,defs,edges,bars,acc,unknown=inspect()
    phases=[]
    for j,(lo,hi) in enumerate(pairwise([-1,*bars,len(rows)])):
        group=[x for x in acc if lo<x['line']<hi]
        addresses={w for x in group if x['words'] for w in x['words']}
        phases.append({'after_barrier':j-1,'loads':sum(x['op']=='Load' for x in group),'stores':sum(x['op']=='Store' for x in group),'unknown':sum(x['words'] is None for x in group),'min':min(addresses,default=None),'max':max(addresses,default=None),'unique_words':len(addresses)})
    report={'group_size':256,'array_words':5120,'all_access_sites':len(acc),'unresolved':dict(unknown),'phases':phases}
    (root/'lds-footprints.json').write_text(json.dumps(report,indent=2)+'\n')
    print('sites',len(acc),'unresolved',sum(unknown.values()),'why',unknown.most_common(5))
    print('phases',[(v['after_barrier'],v['min'],v['max'],v['unique_words']) for v in phases if v['after_barrier']%2==0][:30])
