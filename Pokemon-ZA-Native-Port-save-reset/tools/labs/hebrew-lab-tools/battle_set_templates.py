"""Source-bound factoring of battle messages; no approximate or fuzzy reuse."""
import re

def normalize(source):
    values={}
    text=re.sub(r'\{VAR (?:BD06:0000|BE00)\}', '', source)
    text=re.sub(r'\s+',' ',text).strip()
    def subject(m):
        owner,kind,index=m.groups();tag='@p'+index+'@';he='{VAR 0102:'+index+'}'
        if owner:he+=' של {VAR 0100:'+owner+'}'
        elif kind:he+=' '+('הפראי' if kind=='wild' else 'היריב')
        values.setdefault(tag,[]).append(he)
        return tag
    text=re.sub(r'(?:(?:\{VAR 0100:([0-9A-F]+)\}’s |(?:The|the) (wild|opposing) ))?\{VAR 0102:([0-9A-F]+)\}',subject,text)
    # Owner forms differ syntactically but describe the same stat of the same Pokemon.
    text=re.sub(r'The (Attack|Defense|Sp\. Atk|Sp\. Def|Speed|accuracy|evasiveness) of (@p[0-9A-F]+@)',r'\2’s \1',text)
    return text,values
