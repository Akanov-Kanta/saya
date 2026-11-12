#!/usr/bin/env bash
# Deploys the interactive 3D map (server.py and web/) to the Vercel project "saya-map".
#
#   scripts/deploy_map.sh
#
# The landing page in site/ deploys itself on every push to main (see vercel.json). The map
# cannot share that setup, because the repo root holds only one vercel.json, so this script
# copies the files the server needs into a temporary folder and deploys that folder.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp -d)/saya-map"
mkdir -p "$out"

cd "$root"
git ls-files -z -- '*.py' 'web/*' 'data/*' ':!:tests/*' ':!:main.py' ':!:map_view.py' \
  | rsync -a --from0 --files-from=- ./ "$out/"

# Only what the server imports, at the versions it is tested with.
cat > "$out/requirements.txt" <<'EOF'
osmnx==2.1.1
geopandas==1.2.0
shapely==2.2.0
networkx==3.7
numpy==2.5.4
pandas==3.1.1
pyproj==3.8.0
pyogrio==0.13.0
fastapi==0.162.4
uvicorn==0.54.0
requests==2.34.2
EOF

cd "$out"
vercel link --yes --project saya-map
vercel deploy --prod --yes
