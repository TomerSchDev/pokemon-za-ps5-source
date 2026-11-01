"""Use the existing dispatcher with revision3 and prove every literal verify argv."""
import argparse,hashlib,json
from pathlib import Path
import prepared_species_dispatch as dispatch
dispatch.REVISION='r3'
SUITE=dispatch.SUITE
def verify():
 dispatch.verify_all()
 jobs=dispatch.read(SUITE/'staged-jobs-r2.json')['jobs'];proof=[]
 for job in jobs:
  pin=job['staged_sha256']
  for field in ('launch','verify'):
   args=job[field];assert args[args.index('--staged-sha256')+1]==pin,'Stale exact command pin'
  recipe=SUITE/job['case']/('recipe-r3-'+job['variant']+'.json');value=dispatch.read(recipe)
  assert value['launch']==job['launch'] and value['job']['launch']==job['launch'] and value['job']['verify']==job['verify']
  actual=dispatch.command(job['verify'][1:])
  assert actual['staged_verified'] and actual['all_artifact_sha256_verified'] and actual['game_launched'] is False
  proof.append(dict(case=job['case'],variant=job['variant'],recipe_sha256=dispatch.sha(recipe),staged_sha256=pin,
                    exact_command=job['verify'],actual_result=actual))
  print(json.dumps(dict(command_verified=len(proof),total=20,case=job['case'],variant=job['variant'])),flush=True)
 dispatch.write(SUITE/'exact-command-verification-r3.json',dict(source_sha256=dispatch.sha(Path(__file__)),
  all20_passed=len(proof)==20,game_launched=False,queue_enrolled=False,jobs=proof))
def enqueue():
 proof=dispatch.read(SUITE/'exact-command-verification-r3.json')
 assert proof['all20_passed'] and proof['source_sha256']==dispatch.sha(Path(__file__))
 for job in proof['jobs']:
  recipe=SUITE/job['case']/('recipe-r3-'+job['variant']+'.json')
  assert dispatch.sha(recipe)==job['recipe_sha256']
  assert dispatch.sha(Path(dispatch.read(recipe)['job']['staged']))==job['staged_sha256']
 dispatch.enroll_all()
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('verify','enqueue'));a=parser.parse_args()
 (verify if a.action=='verify' else enqueue)()
