"""Idle-only r22 immutable span experiment; restore exact r21c if needed."""
import deploy
t=deploy.t
t.SOURCE=deploy.ROOT/'artifacts/randomizer-r22-immutable-spans/PPSA91762/eboot.bin'
t.BASE=deploy.ROOT/'artifacts/randomizer-r21c-preparation/PPSA91762/eboot.bin'
t.BASE_SHA='1e7ede8c0f461d99c6a45e34cfb0f555651e5a8a46c7ec83fcd5056654a0f1b1'
t.E=deploy.ROOT/'evidence/preparation-r21-hardware/deployment-r22'
if __name__=='__main__':t.main()
