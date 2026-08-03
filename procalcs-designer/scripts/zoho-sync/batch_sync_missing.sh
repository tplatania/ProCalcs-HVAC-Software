#!/usr/bin/env bash
# Targeted sync — only the 6 communities that failed on www.zohoapis.com timeouts.
# zoho_sync.py now lists via workdrive.zoho.com with retry/backoff.
set -u

DEST=/Users/geraldvillaran/Procalcs/RUPs-from-zoho
INDEX_CSV=$DEST/pairs-index.csv
SCRIPT=/Users/geraldvillaran/Procalcs/envs/jaz-projects/zoho_sync.py

FOLDERS=(
  "ah1hv18550450b4d14a9a9e81ee7ac9e9daa2:Acuera Estates"
  "2df71f9f95a7d130740f988ca566f47f6ccb7:Towns at Riverwalk"
  "bkfhu09d0bd35567f4d74800fa20d0d157c4f:Park View at the Hills"
  "ppqmld0b01d80ab5741b4b6f986a8afd7e085:Pennyroyal"
  "poi3oef35b9979caf419daabbbe2ae26a07e1:Creekside"
  "ocnkcfead557ce5ad449292c51f2a0085493c:General Documents"
)

echo "=========================================="
echo "Missing-communities sync — $(date)"
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
echo "Missing-communities sync complete — $(date)"
find "$DEST" -type f | wc -l | xargs echo "Total files (all communities):"
du -sh "$DEST" | xargs echo "Total size:"
echo "=========================================="
