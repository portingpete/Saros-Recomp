"""Find complete overwrite/read/overwrite intervals eligible for scratch renaming."""
from pathlib import Path
from collections import Counter
import runpy,json,bisect

root=Path(__file__).resolve().parent
parse=runpy.run_path(str(root/'prove-lds-footprints.py'))['inspect']
def choose():
    rows,defs,edges,bars,accesses,unknown=parse()
    assert not unknown
    labels={rid:i for i,(rid,op,a) in enumerate(rows) if op=='Label'}
    shared='%2631'
    permitted=set('AccessChain BitFieldInsert BitFieldSExtract BitFieldUExtract Bitcast BitwiseAnd BitwiseOr BitwiseXor Branch BranchConditional CompositeConstruct CompositeExtract CompositeInsert ConvertFToU ConvertSToF ExtInst FAdd FConvert FDiv FMul FNegate FOrdEqual FOrdGreaterThan FOrdGreaterThanEqual FOrdLessThan FSub GroupNonUniformBallot GroupNonUniformShuffle IAdd IEqual IMul INotEqual ISub IsNan Label Load LogicalAnd LogicalOr Phi SGreaterThanEqual SLessThan Select SelectionMerge ShiftLeftLogical ShiftRightLogical Store ULessThan'.split())
    ext={rid for rid,(op,a) in defs.items() if op=='ExtInstImport' and a==['"GLSL.std.450"']}
    def storage(ptr):
        op,a=defs[ptr]
        if op=='Variable':return a[1]
        if op=='AccessChain':return storage(a[1])
        raise ValueError((ptr,op))
    phases={}
    for j,(lo,hi) in enumerate(zip(bars,bars[1:])):
        group=[x for x in accesses if lo<x['line']<hi]
        allowed=True
        for rid,op,a in rows[lo+1:hi]:
            if op not in permitted:allowed=False;break
            if op=='ExtInst' and (a[1] not in ext or a[2] not in ('Fma','FClamp','FAbs','FMin','FMax','RoundEven','SClamp','UMin','UMax','SMin','SMax','PackHalf2x16','UnpackHalf2x16','NMin','NMax','NClamp')):allowed=False;break
            if op in ('Load','Store'):
                kind=storage(a[1 if op=='Load' else 0])
                if kind not in ('Function','Input','Workgroup') or (op=='Store' and kind=='Input'):allowed=False;break
        if not allowed or not group or any(x['definition']<=lo for x in group):continue
        words={w for x in group for w in x['words']}
        if min(words)<0 or max(words)>=5120:continue
        if all(x['op']=='Load' for x in group):
            phases[j]=('read',words,group);continue
        if any(x['op']!='Store' for x in group):continue
        # Every writer lane must reach every store. Only statically true bounds
        # conditions qualify. Each physical word must have exactly one producer.
        known={x['index']:x['words'] for x in group};i=lo+1;visited=set()
        while i<hi:
            visited.add(i);rid,op,a=rows[i]
            if op=='Branch':i=labels[a[0]]
            elif op=='BranchConditional':
                pred,pa=defs[a[0]]
                if pred!='ULessThan' or pa[1] not in known or pa[2]!='%uint_5120' or max(known[pa[1]])>=5120:break
                i=labels[a[1]]
            else:i+=1
        if i==hi and all(x['line'] in visited for x in group) and len(words)==len(group)*256:
            phases[j]=('write',words,group)
    selected=[];reason=Counter()
    for j in range(2,len(bars)-3,2):
        # The outer guest branch may skip this entire interval. No branch may
        # enter or leave its interior, so all four phases execute together.
        lo,hi=bars[j-1],bars[j+3]
        if any((lo<a<hi)!=(lo<b<hi) or
               (lo<a<b<hi and any(a<cut<b for cut in bars[j:j+3])) for a,b in edges):
            reason['control_flow']+=1;continue
        if any(phases.get(j+o,(None,))[0]!=want for o,want in ((-1,'read'),(0,'write'),(1,'read'),(2,'write'))):
            reason['effects_or_guard']+=1;continue
        written=phases[j][1]
        if not phases[j+1][1]<=written or not written<=phases[j+2][1]:
            reason['incomplete_overwrite']+=1;continue
        if selected and j-selected[-1]['phase']<4:continue
        assert max(written)<1024
        selected.append({'phase':j,'removed':[j,j+2],'words':len(written),'maximum':max(written),
                         'sites':[x['definition'] for x in phases[j][2]+phases[j+1][2]]})
    return rows,bars,selected,reason
if __name__=='__main__':
    rows,bars,selected,reason=choose()
    report={'shader':'b71998dd7f42ee67','source_barriers':len(bars),'selected':selected,'rejected':reason}
    (root/'lds-phase-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print('selected phases',[v['phase'] for v in selected],'barriers saved',2*len(selected),'other reasons',reason)
