"""Decode original converted BNTX textures for read-only material diagnosis."""
import io,json,sys
from pathlib import Path
from run_pc_gallery import ROOT,WORK,Image
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'pokeza-recomp-ps5/third_party/LAS-Randomizer'))
from RandomizerCore.Tools.bntx_editor.bntx_editor import BNTXEditor
source=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data/pm2494/pm2494_00_00'
out=WORK/'diagnostics';out.mkdir(exist_ok=True)
for name in ('BodyA_col','BodyA_lyc','BodyA_amb','Eye_col'):
 p=source/('pm2494_00_'+name+'.bntx');editor=BNTXEditor();editor.openFile(p.read_bytes())
 raw=editor.exportTexByIndex(0);picture=Image.open(io.BytesIO(raw))
 picture.save(out/(name+'.png'));print(name,picture.size,picture.mode,flush=True)
