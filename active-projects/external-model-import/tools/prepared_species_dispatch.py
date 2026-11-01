"""Dispatch one completely prepared fresh species case through the canonical PC FIFO."""
import argparse,json
from prepare_species_suite import fresh_workspace,readiness
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('verify','enqueue'))
    p.add_argument('--workspace',required=True)
    p.add_argument('--case',required=True)
    a=p.parse_args()
    import re
    if not re.fullmatch('[a-z0-9-]+',a.case):p.error('Explicit safe case required')
    result=readiness(fresh_workspace(a.workspace),a.case,a.action=='enqueue')
    print(json.dumps(result,ensure_ascii=True),flush=True)
if __name__=='__main__':main()
