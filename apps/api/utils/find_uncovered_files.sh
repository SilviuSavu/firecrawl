#!/bin/bash

git ls-files > /tmp/all_files.txt

while read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "$line" ]] && continue
  
    pattern=$(echo "$line" | awk '{print $1}')
  
      pattern=${pattern#/}
  
    git ls-files "$pattern" 2>/dev/null >> /tmp/covered_files.txt
done < .github/CODEOWNERS

sort -u /tmp/covered_files.txt > /tmp/covered_files_unique.txt

comm -23 /tmp/all_files.txt /tmp/covered_files_unique.txt

rm /tmp/all_files.txt /tmp/covered_files.txt /tmp/covered_files_unique.txt
