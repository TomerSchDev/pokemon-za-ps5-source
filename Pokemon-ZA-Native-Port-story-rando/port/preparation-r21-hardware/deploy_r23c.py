"""Use the reviewed idle-only startup-config transport for the native read fix."""
import deploy_r23b

t = deploy_r23b.t
t.SOURCE = deploy_r23b.deploy.ROOT / 'artifacts/randomizer-r23c-slot-depth/PPSA91762/eboot.bin'
t.BASE = deploy_r23b.deploy.ROOT / 'artifacts/randomizer-r23b-slot-depth/PPSA91762/eboot.bin'
t.BASE_SHA = '6864e6f40d71408603df3406db7383aff8e8392d1b6fbf86c176e8686f7180ad'
t.E = deploy_r23b.deploy.ROOT / 'evidence/preparation-r21-hardware/deployment-r23c'
if __name__ == '__main__':
    t.main()
