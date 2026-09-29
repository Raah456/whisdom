"""Tokon trial-mission parser -> verified combo routes + per-character cancel table.

The game's own Trial mode. Every route here is one the developers ship as
completable, so unlike the grammar-generated routes these are known to connect.

Two collapses are needed or the routes read as nonsense:
  * jump variants (CmnVJump / CmnBJump / CmnFJump / *HighJump / CmnHomingJump)
    are ALTERNATIVES the trial accepts, not a sequence of seven jumps.
  * SpecialSkillNNNx and SimpleSkillNEx are the motion-input and simple-input
    forms of the SAME move; keeping both doubles every special in the route.
"""
import re, os, json
from collections import defaultdict, Counter

JUMPS = {'CmnVJump','CmnBJump','CmnFJump','CmnVHighJump','CmnBHighJump',
         'CmnFHighJump','CmnHomingJump','CmnAirJump'}

def tokens(path):
    d=open(path,'rb').read()
    return [x.decode() for x in re.findall(rb'[ -~]{2,}',d)]

def parse(path):
    s=tokens(path); missions=[]; cur=None; inlist=False
    for t in s:
        if t=='-MISSION-':
            if cur: missions.append(cur)
            cur={'seq':[],'alts':[],'nums':[],'tags':[]}; inlist=False
        elif cur is None: continue
        elif t=='-LIST-': inlist=True
        elif not inlist: continue
        elif t.startswith('|'): cur['seq'].append(t[1:])
        elif t.startswith('CL_'): pass
        elif t.startswith('+'): cur['alts'].append(t[1:])
        elif re.fullmatch(r'\d+', t): cur['nums'].append(int(t))
        elif t.startswith(('//','-')): pass
        else: cur['tags'].append(t)
    if cur: missions.append(cur)
    return missions

def collapse(seq):
    out=[]
    for m in seq:
        if m in JUMPS:
            if out and out[-1]=='JUMP': continue
            out.append('JUMP'); continue
        # SimpleSkillNEx duplicates the SpecialSkill that precedes it
        if re.fullmatch(r'SimpleSkill(Air)?\dE[A-C]', m) and out and out[-1].startswith(('SpecialSkill','Skill')):
            continue
        out.append(m)
    return out

def pretty(m):
    if m=='JUMP': return 'jump'
    x=re.fullmatch(r'NmlAtk(AIR)?(\d?)([A-E])(\w*)', m)
    if x:
        air='j.' if x.group(1) else ''
        return air+(x.group(2) or '5')+x.group(3)+(f"({x.group(4)})" if x.group(4) else '')
    x=re.fullmatch(r'(Special|Ultimate|Super)Skill(Air)?(\d+)([A-E])(\w*)', m)
    if x:
        air='j.' if x.group(2) else ''
        tag={'Special':'','Ultimate':' ULT','Super':' SUPER'}[x.group(1)]
        return air+x.group(3)+x.group(4)+tag+(f"({x.group(5)})" if x.group(5) else '')
    return m

def build(path, code):
    ms=parse(path); combos=[]; cancels=defaultdict(Counter)
    for i,m in enumerate(ms):
        seq=collapse(m['seq'])
        atk=[x for x in seq if x.startswith(('NmlAtk','SpecialSkill','UltimateSkill','SuperSkill','Shot_'))]
        if len(atk)<2: continue          # single-move tutorials are not combos
        combos.append(dict(mission=i, seq=seq, pretty=[pretty(x) for x in seq],
                           alts=[pretty(a) for a in m['alts']],
                           # 'dam' tag marks a damage-requirement mission; the
                           # threshold is the first number in the block.
                           damage_req=(m['nums'][0] if ('dam' in m['tags'] and m['nums']) else None)))
        prev=None
        for x in seq:
            if x.startswith(('NmlAtk','SpecialSkill','UltimateSkill','Shot_')) or x=='JUMP':
                if prev: cancels[prev][x]+=1
                prev=x
    return combos, {k:dict(v) for k,v in cancels.items()}

if __name__=='__main__':
    out={}
    for f in sorted(os.listdir('trials/raw')):
        code=re.search(r'TrialMissionData_(\w+)\.',f).group(1)
        c,cn=build('trials/raw/'+f, code)
        if c: out[code]=dict(combos=c, cancels=cn)
    json.dump(out, open('trial_combos.json','w'), indent=1)
    tot=sum(len(v['combos']) for v in out.values())
    print(f"characters {len(out)}  verified combo routes {tot}")
    for k in sorted(out): print(f"   {k}: {len(out[k]['combos'])}")
