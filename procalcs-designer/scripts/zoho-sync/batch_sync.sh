#!/usr/bin/env bash
# Batch sync — one community at a time, sequential to avoid Zoho rate-limit deadlock.
# Excludes Canopy (Mustang Way) per user instruction.
set -u

DEST=/Users/geraldvillaran/Procalcs/RUPs-from-zoho
INDEX_CSV=$DEST/pairs-index.csv
SCRIPT=/Users/geraldvillaran/Procalcs/envs/jaz-projects/zoho_sync.py

# id : name pairs, in priority order (partial first so they finish quickly, then fresh)
FOLDERS=(
  "9ddib9b3f6e9313624f2ea34714ff56fea98a:Aulin Square Towns"
  "cpndm662df971e1bb4919bb607930b643c9c5:Windham Park Townhomes"
  "gv6caf38eae1b13d9464e8448a8a1aff90696:Glades at Crossprairie"
  "ohri5baa82f77551b4807b63f1f395eaf97ad:Towns at Greenleaf"
  "jsv3146a007af7b5945a886832411ee497a07:Estates at Lake Jesup"
  "0cmxb32c1c84756ff494ea11fd5a95999d7da:Vintner Reserve"
  "ah1hv18550450b4d14a9a9e81ee7ac9e9daa2:Acuera Estates"
  "2df71f9f95a7d130740f988ca566f47f6ccb7:Towns at Riverwalk"
  "bkfhu09d0bd35567f4d74800fa20d0d157c4f:Park View at the Hills"
  "ppqmld0b01d80ab5741b4b6f986a8afd7e085:Pennyroyal"
  "poi3oef35b9979caf419daabbbe2ae26a07e1:Creekside"
  "ocnkcfead557ce5ad449292c51f2a0085493c:General Documents"
)

echo "=========================================="
echo "Batch Zoho sync — $(date)"
echo "12 folders, sequential. Canopy excluded."
echo "=========================================="

for entry in "${FOLDERS[@]}"; do
  folder_id="${entry%%:*}"
  folder_name="${entry#*:}"
  echo ""
  echo "########## [$(date '+%H:%M:%S')] $folder_name ##########"
  mkdir -p "$DEST/$folder_name"
  python3 -u "$SCRIPT" \
    --folder "$folder_id" \
    --dest "$DEST/$folder_name" \
    --extensions .rup,.xls,.xlsx \
    --exclude-re \
    --index-csv "$INDEX_CSV" 2>&1
  status=$?
  if [ $status -ne 0 ]; then
    echo "!!! $folder_name exited with status $status — continuing to next folder"
  fi
done

echo ""
echo "=========================================="
echo "Batch sync complete — $(date)"
find "$DEST" -type f | wc -l | xargs echo "Total files:"
du -sh "$DEST" | xargs echo "Total size:"
echo "=========================================="
