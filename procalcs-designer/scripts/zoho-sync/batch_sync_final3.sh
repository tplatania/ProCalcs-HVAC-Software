#!/usr/bin/env bash
# Final pass — the 3 communities whose walks died mid-run.
# zoho_sync.py now retries downloads AND survives failed subtrees.
set -u

DEST=/Users/geraldvillaran/Procalcs/RUPs-from-zoho
INDEX_CSV=$DEST/pairs-index.csv
SCRIPT=/Users/geraldvillaran/Procalcs/envs/jaz-projects/zoho_sync.py

FOLDERS=(
  "bkfhu09d0bd35567f4d74800fa20d0d157c4f:Park View at the Hills"
  "ppqmld0b01d80ab5741b4b6f986a8afd7e085:Pennyroyal"
  "poi3oef35b9979caf419daabbbe2ae26a07e1:Creekside"
)

echo "=========================================="
echo "Final-3 sync — $(date)"
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
echo "Final-3 sync complete — $(date)"
find "$DEST" -type f | wc -l | xargs echo "Total files (all communities):"
du -sh "$DEST" | xargs echo "Total size:"
echo "=========================================="
