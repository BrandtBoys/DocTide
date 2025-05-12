#!/bin/sh -l

# Install Git
apt-get update
apt-get install -y git
apt-get install -y curl
apt-get install -y procps

# Tell the action to trust github/workspace - to avoid "dubious ownership"
git config --global --add safe.directory /github/workspace

# Login on git with DocTide bot
git config --global user.name "DocTide[bot]"
git config --global user.email "DocTide[bot]@users.noreply.github.com"
git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git

# Install doctide.py dependencies
pip install -r /requirements_doctide.txt

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve > /dev/null 2>&1 &
OLLAMA_PID=$!

# Wait for Ollama API to become available
echo "Waiting for Ollama to be ready..."
until curl -s http://127.0.0.1:11434 > /dev/null; do
  sleep 1
done
echo "Ollama is ready!"

# Pull Ollama model
ollama pull llama3.2 

top -b -d 1 -p $(pgrep -f 'ollama serve') >> /tmp/resource_usage.log &
TOP_PID=$!

# Run Doctide agent
python /doctide.py $1

# Stop monitoring after run
kill $TOP_PID

# Analyze usage summary if in test mode
if [ "$1" = "true" ]
then
    echo "===== Analyzing Ollama CPU & RAM usage ====="

    OLLAMA_PID=$(pgrep -f 'ollama serve')

    grep "$OLLAMA_PID root" /tmp/resource_usage.log | awk '
    {
        cpu+=$9;
        mem+=$10;
        if ($9>cpu_max) cpu_max=$9;
        if ($10>mem_max) mem_max=$10;
        if (cpu_min=="" || $9<cpu_min) cpu_min=$9;
        if (mem_min=="" || $10<mem_min) mem_min=$10;
        count++;
    }
    END {
        if (count>0) {
            printf "\n=== Ollama Usage Summary ===\n";
            printf "CPU usage:  min: %.1f%%  avg: %.1f%%  max: %.1f%%\n", cpu_min, cpu/count, cpu_max;
            printf "MEM usage:  min: %.1f%%  avg: %.1f%%  max: %.1f%%\n", mem_min, mem/count, mem_max;
        } else {
            print "No usage data found for Ollama process."
        }
    }'

    echo "===== Done ====="

    # Proceed with test mode git ops
    git checkout "${GITHUB_REF#refs/heads/}"
    git fetch origin "$BRANCH_NAME"
    git merge origin/"$BRANCH_NAME"
    git push -d origin "$BRANCH_NAME"
    git fetch origin "${GITHUB_REF#refs/heads/}"
    git push origin HEAD
else
    gh auth setup-git
    gh pr create -B main -H "$BRANCH_NAME" --fill-first
fi