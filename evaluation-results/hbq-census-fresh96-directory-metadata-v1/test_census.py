"""One guard for opaque schedule fields and exact directory membership."""
import json,unittest
import census

class Boundary(unittest.TestCase):
    def test_opaque_fields_and_wrong_directory(self):
        cells=[{'cell_id':f'cell-{candidate}-{item}','candidate_id':candidate,'item_id':f'item-{item}',
                'prompt_group_id':f'group-{item//2}'} for candidate in ('a','b') for item in range(32)]
        value={'study_id':'synthetic','schedule_sha256':'synthetic','cells':cells}
        raw=json.dumps(value).encode().replace(b'"cells":',b'"payload":"\\q", "human_target":"\\q", "cells":')
        with self.assertRaises(json.JSONDecodeError):json.loads(raw)
        projected=census.projector()(raw,census.SELECTOR)
        self.assertEqual(projected,value)
        names=[census.directory_id(cell['cell_id']) for cell in cells]
        expected=dict(cells=64,candidates=2,items=32,prompt_groups=16)
        self.assertEqual(len(census.join(projected,names,expected)),64)
        with self.assertRaisesRegex(ValueError,'Directory/schedule membership'):
            census.join(projected,names[:-1]+['v10-sol-wrong'],expected)

if __name__=='__main__':unittest.main()
