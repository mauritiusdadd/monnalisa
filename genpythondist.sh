#!/usr/bin/bash
 
version="$(git describe)"
package_year="$(date +%Y)"

echo "Program version: ${version} - ${package_year}"

checkpoint="$(git stash create)"
echo " - created checkpoint: ${checkpoint}"

echo " - setting project properties ..."
perl -i -pe "s/\\\${PACKAGE_YEAR}/${package_year}/g;" COPYRIGHT

find . -name "*.py" -exec perl -i \
-pe 's/\${LICENSE_HEADER}/`cat COPYRIGHT`/e;' \
-pe "s/\\\${PROGRAM_VERSION}/${version##v}/g;" {} \;

echo " - building dist package ..."
python setup.py sdist --formats=gztar,zip &> /dev/null

echo " - resrotring checkpoint ..."
git stash push -q
[ -z "${checkpoint}" ] || git stash apply -q ${checkpoint}
git stash drop -q
