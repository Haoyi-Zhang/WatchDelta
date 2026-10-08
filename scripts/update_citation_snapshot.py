#!/usr/bin/env python3
"""Regenerate the retained paper citation snapshot for standalone audit."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
ENTRY_RE=re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,",re.MULTILINE)
CITE_RE=re.compile(r"\\cite\w*\s*\{([^}]*)\}")
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--paper',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
 paper=a.paper.resolve();out=a.output or Path(__file__).resolve().parents[1]/'evidence/paper-citation-snapshot.json'
 bib=paper/'references.bib';keys=sorted(ENTRY_RE.findall(bib.read_text(encoding='utf-8')))
 files=[paper/'main.tex',*sorted((paper/'sections').glob('*.tex'))]
 tex='\n'.join(f.read_text(encoding='utf-8') for f in files)
 cited=sorted({k.strip() for m in CITE_RE.finditer(tex) for k in m.group(1).split(',') if k.strip()})
 payload={'classification':'paper citation-key snapshot for standalone artifact verification','bibliography_entries':len(keys),'bibliography_keys':keys,'cited_keys':cited,'all_entries_cited':set(keys)==set(cited),'paper_main_sha256':sha(paper/'main.tex'),'paper_section_sha256':{f.name:sha(f) for f in sorted((paper/'sections').glob('*.tex'))},'bibliography_sha256':sha(bib)}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'output':str(out),'entries':len(keys),'cited':len(cited),'all_entries_cited':payload['all_entries_cited']},indent=2))
if __name__=='__main__':main()
