"""Unit/negative tests and real numerical-extract checks, not live pipeline tests."""
from __future__ import annotations
import ast
import copy
import json
import math
import stat
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_train119_diagnostic as v
import export_train119_from_owner_zip as e


def fixture(q=0.0, energy=-1949.0, subset='neb9', index=1):
    xyz=[[0,0,0],[1+q/2,0,0],[0,1,0],[0,2,0],[1,1,0],[1,2,0],[2,1,0],[2,0,0],[2,2,0]]
    rows=['BEGIN_CFG','Size','9','Supercell','16 0 0','0 16 0','0 0 16',
          'AtomData: id type cartes_x cartes_y cartes_z fx fy fz']
    for i,(t,p) in enumerate(zip(v.TYPES,xyz),1):
        rows.append(' '.join(map(str,[i,t,*p,0.1,0.2,0.3])))
    rows+=['Energy',str(energy),f'Feature audit_id {subset}_{index}',f'Feature audit_subset {subset}',
           f'Feature audit_subset_index {index}',f'Feature q_pt_A {q}','END_CFG']
    return '\n'.join(rows)+'\n'


def pw_fixture():
    r={'pbe_energy_Ry_raw':-143.3,'pbe_forces_Ry_bohr':[[0.01,0.02,0.03] for _ in range(9)]}
    head=f"!    total energy = {r['pbe_energy_Ry_raw']:.8f} Ry\nconvergence has been achieved in 37 iterations\n"
    head+='Forces acting on atoms (cartesian axes, Ry/au):\n\n'
    rows=[f'atom {i} type {t+1} force = {f[0]:.8f} {f[1]:.8f} {f[2]:.8f}' for i,(t,f) in enumerate(zip(v.TYPES,r['pbe_forces_Ry_bohr']),1)]
    return head+'\n'.join(rows)+'\nThe non-local contrib. to forces\natom 1 type 3 force = 999 999 999\nJOB DONE.\n'


def xml_fixture():
    cfg=v.parse_cfg(fixture())[0]
    root=ET.Element('espresso');out=ET.SubElement(root,'output')
    conv=ET.SubElement(ET.SubElement(out,'convergence_info'),'scf_conv')
    ET.SubElement(conv,'convergence_achieved').text='true'
    structure=ET.SubElement(out,'atomic_structure');positions=ET.SubElement(structure,'atomic_positions')
    for t,xyz in zip(cfg.types,cfg.xyz):
        ET.SubElement(positions,'atom',name=v.ELEMENT[t]).text=' '.join(str(x/v.BOHR_A) for x in xyz)
    cell=ET.SubElement(structure,'cell')
    for k,row in zip(['a1','a2','a3'],cfg.cell):ET.SubElement(cell,k).text=' '.join(str(x/v.BOHR_A) for x in row)
    total=ET.SubElement(out,'total_energy');ET.SubElement(total,'etot').text=str(cfg.energy/(2*v.RY_EV))
    ET.SubElement(out,'forces').text=' '.join(str(x*v.BOHR_A/(2*v.RY_EV)) for row in cfg.forces for x in row)
    return cfg,root


def qe_input_fixture():
    c=v.parse_cfg(fixture())[0]
    lines=["&CONTROL"," calculation='scf', tprnfor=.true.,","/","&SYSTEM",
           " ibrav=0, nat=9, ntyp=3, ecutwfc=80, ecutrho=960,",
           " occupations='fixed', input_dft='PBE', tot_charge=0, nspin=1, nosym=.true., noinv=.true.,",
           "/","&ELECTRONS"," conv_thr=1d-10,","/","ATOMIC_SPECIES",
           "C 12.011 C.pbe-n-kjpaw_psl.1.0.0.UPF","H 1.008 H.pbe-kjpaw_psl.1.0.0.UPF","O 15.999 O.pbe-n-kjpaw_psl.1.0.0.UPF",
           "CELL_PARAMETERS angstrom","16 0 0","0 16 0","0 0 16","ATOMIC_POSITIONS angstrom"]
    lines += [v.ELEMENT[t]+' '+' '.join(map(str,xyz)) for t,xyz in zip(c.types,c.xyz)]
    lines += ['K_POINTS gamma']
    return c,'\n'.join(lines)+'\n'

class Parsers(unittest.TestCase):
    def test_declared_pbe_input(self):
        c,text=qe_input_fixture();self.assertTrue(v.pw_input_declaration(text,c)['declared_setup_pass'])
    def test_wrong_pbe_cutoff(self):
        c,text=qe_input_fixture()
        with self.assertRaises(v.AuditError):v.pw_input_declaration(text.replace('ecutwfc=80','ecutwfc=20'),c)
    def test_wrong_pbe_input_units(self):
        c,text=qe_input_fixture()
        with self.assertRaises(v.AuditError):v.pw_input_declaration(text.replace('ATOMIC_POSITIONS angstrom','ATOMIC_POSITIONS bohr'),c)
    def test_wrong_pseudopotential_name(self):
        c,text=qe_input_fixture()
        with self.assertRaises(v.AuditError):v.pw_input_declaration(text.replace('H.pbe-kjpaw_psl.1.0.0.UPF','H.other.UPF'),c)

    def test_valid_cfg(self):self.assertEqual(len(v.parse_cfg(fixture(),labels=True)),1)
    def test_missing_end(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('END_CFG',''))
    def test_nested_begin(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('Size','BEGIN_CFG\nSize'))
    def test_unmatched_end(self):
        with self.assertRaises(v.AuditError):v.parse_cfg('END_CFG\n'+fixture())
    def test_nonfinite_force(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('0.1 0.2 0.3','nan 0.2 0.3',1))
    def test_duplicate_ids(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('2 1 1.0','1 1 1.0',1))
    def test_wrong_types(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('1 2 0 0 0','1 0 0 0 0',1))
    def test_duplicate_features(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('END_CFG','Feature audit_id other\nEND_CFG'))
    def test_extra_atom_row(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace("Energy\n","10 1 3 3 3 0 0 0\nEnergy\n",1))
    def test_duplicate_energy(self):
        with self.assertRaises(v.AuditError):v.parse_cfg(fixture().replace('END_CFG','Energy\n-100\nEND_CFG'))
    def test_missing_forces(self):
        c=v.parse_cfg(fixture())[0]
        self.assertEqual(len(c.forces),9)
        with self.assertRaises(v.AuditError):v.force_metrics(c.forces[:-1],c.forces)
    def test_force_shape_truncation(self):
        with self.assertRaises(v.AuditError):v.force_metrics([[1,2]]*9,[[1,2,3]]*9)
    def test_geometry_changed(self):
        a=v.parse_cfg(fixture())[0];b=copy.deepcopy(a);b.xyz[0][0]+=1e-3
        self.assertFalse(v.geometry_guard(a,b)['pass_guard'])
    def test_valid_pw_excludes_contributions(self):
        _,f,_=v.terminal_pw(pw_fixture());self.assertLess(max(map(abs,f[0])),2)
    def test_missing_done(self):
        with self.assertRaises(v.AuditError):v.terminal_pw(pw_fixture().replace('JOB DONE.','unfinished'))
    def test_duplicate_done(self):
        with self.assertRaises(v.AuditError):v.terminal_pw(pw_fixture()+'JOB DONE.\n')
    def test_nonconverged(self):
        with self.assertRaises(v.AuditError):v.terminal_pw(pw_fixture()+'convergence NOT achieved\n')
    def test_missing_official_header(self):
        with self.assertRaises(v.AuditError):v.terminal_pw(pw_fixture().replace('Forces acting on atoms','Contribution'))
    def test_official_truncation_not_completed_with_contribution(self):
        text='\n'.join(s for s in pw_fixture().splitlines() if not s.startswith('atom 9 '))
        with self.assertRaises(v.AuditError):v.terminal_pw(text)
    def test_pw_species(self):
        with self.assertRaises(v.AuditError):v.terminal_pw(pw_fixture().replace('atom 1 type 3','atom 1 type 1',1))
    def test_valid_xml(self):
        c,r=xml_fixture();en,f=v.xml_reference(ET.tostring(r).decode(),c)
        self.assertAlmostEqual(en,c.energy,places=10);self.assertLess(v.maxdelta(f,c.forces),1e-14)
    def test_xml_geometry_error(self):
        c,r=xml_fixture();r.find('output/atomic_structure/atomic_positions/atom').text='1 2 3'
        with self.assertRaises(v.AuditError):v.xml_reference(ET.tostring(r).decode(),c)
    def test_xml_force_count(self):
        c,r=xml_fixture();r.find('output/forces').text='1 2 3'
        with self.assertRaises(v.AuditError):v.xml_reference(ET.tostring(r).decode(),c)
    def test_xml_species(self):
        c,r=xml_fixture();r.find('output/atomic_structure/atomic_positions/atom').set('name','C')
        with self.assertRaises(v.AuditError):v.xml_reference(ET.tostring(r).decode(),c)
    def test_missing_central_does_not_fallback(self):
        text=''.join(fixture(q=.4,subset='basin12',index=i) for i in range(1,13))
        text+=''.join(fixture(q=q,index=i) for i,q in enumerate([-.4,-.3,-.2,-.18,0,.18,.2,.3,.4],1))
        x=v.parse_cfg(text)
        with self.assertRaisesRegex(v.AuditError,'no fallback'):v.static_metrics(x,x)
    def test_central_membership_valid(self):
        text=''.join(fixture(q=.4,subset='basin12',index=i) for i in range(1,13))
        text+=''.join(fixture(q=q,index=i) for i,q in enumerate([-.4,-.3,-.2,-.1,0,.1,.2,.3,.4],1))
        x=v.parse_cfg(text);self.assertEqual(v.static_metrics(x,x)['transition_indices_1based'],[16,17,18])
    def test_qpt_metadata_mismatch(self):
        text=''.join(fixture(q=.4,subset='basin12',index=i) for i in range(1,13))
        text+=''.join(fixture(q=q,index=i) for i,q in enumerate([-.4,-.3,-.2,-.1,0,.1,.2,.3,.4],1))
        x=v.parse_cfg(text);x[12].features['q_pt_A']='0'
        with self.assertRaisesRegex(v.AuditError,'qPT'):v.static_metrics(x,x)

class ExportSafety(unittest.TestCase):
    def test_member_traversal(self):
        with self.assertRaises(v.AuditError):e.safe_member('../x')
    def test_member_absolute(self):
        with self.assertRaises(v.AuditError):e.safe_member('/x')
    def test_member_windows(self):
        with self.assertRaises(v.AuditError):e.safe_member('C:/x')
    def test_member_symlink(self):
        with self.assertRaises(v.AuditError):e.safe_member('x',stat.S_IFLNK)
    def test_protected_name_rejected_without_reading_payload(self):
        with self.assertRaises(v.AuditError):e.safe_member('synthetic/Blind12.cfg')
    def test_allowlist_excludes_restricted_files(self):
        selected=e.selection();self.assertGreater(len(selected),40)
        self.assertFalse(any(x.lower().endswith(('.upf','.exe','.dll','.ttf','.woff')) for x in selected.values()))
        self.assertFalse(any('prompt' in x.lower() or '/BUILD/' in x for x in selected.values()))
    def test_sanitized_cfg_keeps_numbers_and_historical_flag(self):
        home=str(Path('/','home','example_user'))
        src=fixture().replace('END_CFG',f'Feature training_eligible false\nFeature source {home}/project\nEND_CFG').encode()
        dest=e.sanitize(src,'.cfg');self.assertNotIn(home.encode(),dest)
        a=v.parse_cfg(src.decode())[0];b=v.parse_cfg(dest.decode())[0]
        self.assertEqual(a.xyz,b.xyz);self.assertEqual(b.features['training_eligible'],'false')
    def test_sanitized_json_keeps_numbers(self):
        x={'seed':13213601879837099893,'stop':1.0000012996964838,'path':str(Path('/','home','example_user','path'))}
        y=json.loads(e.sanitize(json.dumps(x).encode(),'.json'))
        self.assertEqual(x['seed'],y['seed']);self.assertEqual(x['stop'],y['stop'])
    def test_missing_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):v.verify(Path(d))
    def test_no_scientific_execution_imports_or_assert_gates(self):
        for path in (ROOT/'tools/verify_train119_diagnostic.py', ROOT/'tools/export_train119_from_owner_zip.py'):
            tree=ast.parse(path.read_text())
            self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)),path.name)
            imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            imports+=[i.name for n in ast.walk(tree) if isinstance(n,ast.Import) for i in n.names]
            self.assertFalse(set(imports)&{'subprocess','requests','socket','urllib.request','os'},path.name)

if __name__=='__main__':unittest.main(verbosity=2)
