"""Subset the public BOEM File Request System inventory (FRSWellDataRawData.zip, mv_frs_file_inventory.txt) to the
digital log files ("raw-" document IDs) of the Gulf exploration wells inside NAMSS 3D outlines. Also counts all
raw-log files in the inventory for the index summary. Runs on lambda-scalar, reads only, writes ~/osd-build/.

    python3 frs_subset_lambda.py
"""
import collections, csv, json, os

HOME = os.path.expanduser('~')
INV = f'{HOME}/veles-toy-basin/gulf_data/extracted/boem_frs/FRSWellDataRawData/mv_frs_file_inventory.txt'
WELLS = f'{HOME}/veles-toy-basin/gulf_logs/explo_wells.csv'
OUT = f'{HOME}/osd-build'

wells = {r['api'][:10]: r for r in csv.DictReader(open(WELLS)) if r['surveys']}
keep, stats = [], collections.Counter()
apis_raw = set()
for r in csv.DictReader(open(INV, encoding='latin-1')):
    did = r['DOC_ID']
    if not did.startswith('raw-'):
        stats['other_files'] += 1
        continue
    stats['raw_files'] += 1
    stats['raw_bytes'] += int(r['FILE_SIZE'] or 0)
    apis_raw.add(r['API'][:10])
    if r['API'][:10] in wells:
        keep.append(dict(doc_id=did, api=r['API'], api10=r['API'][:10], doc_type=r['DOC_TYPE'], run_date=r['RUN_DATE'],
                         releasable_date=r['RELEASABLE_DATE'], file_ext=r['FILE_EXT'], bytes=int(r['FILE_SIZE'] or 0),
                         created_date=r['CREATED_DATE']))
stats['wells_with_raw_any'] = len(apis_raw)
stats['explo_wells_in_namss'] = len(wells)
stats['explo_wells_in_namss_with_raw'] = len({k['api10'] for k in keep})
after = {a for a, w in wells.items() if w['after_survey'] == 'True'}
stats['after_survey_wells'] = len(after)
stats['after_survey_wells_with_raw'] = len({k['api10'] for k in keep if k['api10'] in after})
stats['after_survey_raw_files'] = sum(1 for k in keep if k['api10'] in after)
stats['after_survey_raw_bytes'] = sum(k['bytes'] for k in keep if k['api10'] in after)
stats['after_survey_raw_files_le_100MB'] = sum(1 for k in keep if k['api10'] in after and k['bytes'] <= 100e6)
stats['after_survey_raw_bytes_le_100MB'] = sum(k['bytes'] for k in keep if k['api10'] in after and k['bytes'] <= 100e6)
stats['file_ext'] = dict(collections.Counter(k['file_ext'] for k in keep).most_common(15))
stats['doc_type'] = dict(collections.Counter(k['doc_type'] for k in keep).most_common(15))
os.makedirs(OUT, exist_ok=True)
with open(f'{OUT}/boem_frs_raw_logs.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, list(keep[0]))
    w.writeheader()
    w.writerows(keep)
json.dump(stats, open(f'{OUT}/frs_stats.json', 'w'), indent=1)
print(json.dumps(stats, indent=1))
