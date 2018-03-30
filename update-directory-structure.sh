#!/bin/bash


md5_for()
{
  if builtin command -v md5 > /dev/null; then
    echo "$1" | md5
  elif builtin command -v md5sum > /dev/null ; then
    echo "$1" | md5sum | awk '{print $1}'
  else
    echo "Neither md5 nor md5sum were found in the PATH"
    return 1
  fi

  return 0
}

# Check if we are in the right directory
ROOT=$(pwd)
if [[ "$ROOT" != *repository.marcelveldt ]]
then
  echo -e "Run this script inside the repository's root directory!"
  exit 1
fi
echo "Root Path: ${ROOT}"

# Generate md5 checksum for every .zip file
for ZIP in $(find ${ROOT} -name '*.zip'); do
   filename=${ZIP} | grep -o '^\S*' > ${ZIP}.md5
   md5_for $filename
   echo "Updated ${ZIP}.md5"
done

# Update addons.xml md5 checksum
filename=${ROOT}/addons.xml | grep -o '^\S*' > ${ROOT}/addons.xml.md5
md5_for $filename
echo "Updated ${ROOT}/addons.xml.md5"

# Generate index.html files
for DIR in $(find ${ROOT} -path ${ROOT}/.git -prune -o -type d); do
  (
  echo -e "<html>\n<body>\n<h1>Directory listing</h1>\n<hr/>\n<pre>"
  ls "${DIR}" | grep -v "^\./$" | grep -v "^index\.html$"  | awk '{ printf "<a href=\"%s\">%s</a>\n",$1,$1 }'
  echo -e "</pre>\n</body>\n</html>"
  ) > "${DIR}/index.html"
  echo "Updated ${DIR}/index.html"
done
