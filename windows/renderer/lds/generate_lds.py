"""Generate a private replacement module and header from an exact user-supplied module."""
from pathlib import Path
from itertools import accumulate
from difflib import SequenceMatcher
import argparse, hashlib, json, os, runpy, struct, subprocess
import xxhash
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--module',type=Path,required=True)
parser.add_argument('--grammar',type=Path,required=True)
parser.add_argument('--spirv-dis',type=Path,required=True)
parser.add_argument('--spirv-val',type=Path,required=True)
parser.add_argument('--private-output',type=Path,required=True)
args=parser.parse_args()
out=args.private_output.resolve();out.mkdir(parents=True,exist_ok=True)
for name in ('private-input.asm', 'private-generated.spv', 'SarosLds.h'):
    if (out/name).exists():
        raise SystemExit('refusing to overwrite existing private output: '+name)
before=args.module.resolve();original=before.read_bytes()
sha=lambda data:hashlib.sha256(data).hexdigest()
if sha(original)!='6cd3bcf93c0a0f72855a0d979a5643618377cc3841ac71fa8055d2f21e4f1835':
    raise SystemExit('unsupported input module SHA-256')
asm=out/'private-input.asm'
subprocess.run([str(args.spirv_dis),str(before),'-o',str(asm)],check=True)
os.environ['LDS_INPUT_ASM']=str(asm)
ops={v['opname'].removeprefix('Op'):v['opcode'] for v in json.loads(args.grammar.read_text(encoding='utf-8'))['instructions']}
validator=args.spirv_val
def tool(name,*a):
    if name!='spirv-val':raise ValueError(name)
    subprocess.run([str(validator),*[str(x) for x in a]],check=True)
rows,bars,selected,reason=runpy.run_path(str(root/'choose-lds-phases.py'))['choose']()
program='private-generated'
private=True
binary=struct.unpack('<%dI'%(len(original)//4),original)
assert binary[1]==0x10300
array_id,ptr_id,var_id=range(binary[3],binary[3]+3)
skip={bars[n] for p in selected for n in p['removed']}
move={i for phase in selected for i in phase['sites']}
length=max(p['maximum'] for p in selected)+1
assert len(selected)>=8 and length==1024
names={};words=list(binary[:5]);words[3]=var_id+1
if private:
    rows2,defs,edges,bars2,accesses,unknown=runpy.run_path(str(root/'prove-lds-footprints.py'))['inspect']()
    assert rows==rows2 and bars==bars2 and not unknown
    bank_def={};bank_use={};owners={}
    for s in accesses:
        if max(s['words'])<length:continue
        bank=s['words'][0]//256
        assert 4<=bank<20 and all(w==bank*256+lane for lane,w in enumerate(s['words']))
        assert s['definition'] not in move
        bank_def[s['definition']]=bank;bank_use[s['line']]=bank
        owners.setdefault(bank,[]).append(s['op'])
    assert set(owners)==set(range(4,20)) and all(v.count('Store')==1 and v.count('Load')>=1 for v in owners.values())
    assert len(bank_def)==len(bank_use)==48
    locals_by_bank={k:var_id+1+k-4 for k in owners}
    words[3]=max(locals_by_bank.values())+1
    pc=5;const_inst=None
    for rid,op,a in rows:
        n=binary[pc]>>16
        if rid=='%uint_1024':const_inst=list(binary[pc:pc+n])
        pc+=n
    assert const_inst[-1]==1024 and pc==len(binary)
cursor=5
def emit(op,*a):words.extend([((len(a)+1)<<16)|ops[op],*a])
seen=[0,0,0]
for i,(rid,op,args) in enumerate(rows):
    head=binary[cursor];n=head>>16
    assert head&65535==ops[op] and n!=0
    inst=list(binary[cursor:cursor+n]);cursor+=n
    if rid=='%uint':
        assert op=='TypeInt' and inst[2:]==[32,0];names[rid]=inst[1]
    if private and rid=='%_arr_uint_uint_5120':
        assert op=='TypeArray' and inst[2]==names['%uint']
        words.extend(const_inst);inst[3]=const_inst[2]
    if rid=='%uint_1024':
        assert op=='Constant' and inst[1]==names['%uint'] and inst[3:]==[length]
        names[rid]=inst[2]
        if private:continue
    if rid=='%2631':
        assert op=='Variable' and inst[3:]==[4];names[rid]=inst[2]
        names['wg_pointer_type']=inst[1]
    if rid=='%_ptr_Function_uint':
        assert op=='TypePointer' and inst[2:]==[7,names['%uint']]
        names['private_pointer_type']=inst[1]
    if op=='Function':
        if private:emit('Variable',names['wg_pointer_type'],var_id,4)
        else:
            emit('TypeArray',array_id,names['%uint'],names['%uint_1024'])
            emit('TypePointer',ptr_id,4,array_id)
            emit('Variable',ptr_id,var_id,4)
        seen[0]+=1
    if private and rid=='%89':
        assert op=='Variable' and inst[3:]==[7] and inst[1]==names['private_pointer_type']
        for private_id in locals_by_bank.values():emit('Variable',inst[1],private_id,7)
    if private and i in bank_def:
        assert op=='AccessChain' and inst[3]==names['%2631']
        continue
    if private and i in bank_use:
        assert op in ('Load','Store');inst[3 if op=='Load' else 1]=locals_by_bank[bank_use[i]]
    if i in move:
        assert op=='AccessChain' and len(inst)==5 and inst[3]==names['%2631']
        inst[3]=var_id;seen[1]+=1
    if i in skip:
        assert op=='ControlBarrier' and len(inst)==4;seen[2]+=1
    else:words.extend(inst)
assert cursor==len(binary) and seen==[1,len(move),len(skip)] and len(skip)==2*len(selected)
candidate=struct.pack('<%dI'%len(words),*words)
module=out/(program+'.spv');module.write_bytes(candidate)
tool('spirv-val','--target-env','vulkan1.3','--uniform-buffer-standard-layout',module)

before=original
after=candidate
def instructions(data):
    words=struct.unpack('<%dI'%(len(data)//4),data)
    items=[words[:5]];p=5
    while p<len(words):
        n=words[p]>>16;assert n and p+n<=len(words)
        items.append(words[p:p+n]);p+=n
    return words,items,list(accumulate(map(len,items),initial=0))
original,left,lo=instructions(before);candidate,right,ro=instructions(after)
edits=[];payload=[];reconstructed=[];src=0
for what,i,j,x,y in SequenceMatcher(None,left,right,autojunk=False).get_opcodes():
    if what=='equal':continue
    a,b=lo[i],lo[j]
    replacement=candidate[ro[x]:ro[y]]
    reconstructed.extend(original[src:a]);reconstructed.extend(replacement);src=b
    edits.append((a,b-a,len(payload),len(replacement)));payload.extend(replacement)
reconstructed.extend(original[src:])
assert tuple(reconstructed)==candidate
def signature(data):
    h=xxhash.xxh3_128_intdigest(data)
    return '{0x%016xULL, 0x%016xULL}'%(h&((1<<64)-1),h>>64)
source='''#pragma once
#include <algorithm>
#include <cstdint>
#include <span>
#include <vector>
#include <xxhash.h>

namespace SarosLds {
struct Edit { uint32_t start, remove, payloadStart, payloadSize; };
'''
source+='inline constexpr Edit edits[] = {\n'+''.join('    {%d, %d, %d, %d},\n'%e for e in edits)+'};\n'
source+='inline constexpr uint32_t replacements[] = {\n'+''.join('    '+', '.join(str(w)+'u' for w in payload[i:i+10])+',\n' for i in range(0,len(payload),10))+'};\n'
source+=f'inline constexpr size_t originalWords = {len(original)};\ninline constexpr size_t candidateWords = {len(candidate)};\n'
source+='inline constexpr XXH128_hash_t originalHash = '+signature(before)+';\n'
source+='inline constexpr XXH128_hash_t candidateHash = '+signature(after)+';\n'
source+='''
// The address proof covers only this specific module. Preserve every other input.
inline std::vector<uint32_t> Apply(std::span<const uint32_t> code) {
    if (code.size()!=originalWords || !XXH128_isEqual(XXH3_128bits(code.data(),code.size_bytes()),originalHash)) return {};
    std::vector<uint32_t> patched;
    patched.reserve(candidateWords);
    size_t cursor=0;
    for (const auto& edit:edits) {
        patched.insert(patched.end(),code.begin()+cursor,code.begin()+edit.start);
        patched.insert(patched.end(),replacements+edit.payloadStart,replacements+edit.payloadStart+edit.payloadSize);
        cursor=edit.start+edit.remove;
    }
    patched.insert(patched.end(),code.begin()+cursor,code.end());
    if (patched.size()!=candidateWords || !XXH128_isEqual(XXH3_128bits(patched.data(),patched.size()*sizeof(uint32_t)),candidateHash)) return {};
    return patched;
}
}
'''
(out/'SarosLds.h').write_text(source, encoding='utf-8')

print(json.dumps({'original_sha256':sha(before),'candidate_sha256':sha(after),
 'header_sha256':sha((out/'SarosLds.h').read_bytes()),'phase_count':len(selected),
 'removed_barriers':len(skip),'private_accesses':len(bank_use),
 'warning':'Output module, assembly and header contain game-derived shader data; keep private.'},indent=2))
