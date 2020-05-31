#!/usr/bin/env bash
#
# usage: dump-sql-tables-to-csv.sh [-d database] [-h hostname] [-p port] [-m <1|0>] [-n ndays]

trap "cleanup 1" SIGINT
set -o pipefail

# Temporary directory where we dump MySQL tables to CSV files.
TMPDIR=`mktemp -d -t XXXX`
MYSQL_TABLES=

function cleanup() {
	local code=$1
	# Remove CSV files.
	for tbl in ${MYSQL_TABLES}; do
		rm -f ${TMPDIR}/${tbl}.csv
	done
	# Remove temporary directory housings CSV files.
	if [ -d "${TMPDIR}" ]; then
		rm -rf ${TMPDIR}
	fi
	exit $code
}

# Identify column in each table that we can reference to index records chronologically.
function datetime_column() {
	local tbl=$1
	# XXX in bash 4.x, just use associative arrays.
	IDX=0
	case $tbl in
		'fills') IDX=0;;
		'decisions') IDX=1;;
		'orders') IDX=2;;
		'positions') IDX=3;;
		'tradeBin1m') IDX=4;;
	esac
	colnames=("transaction_dt" "timestamp_dt" "created_dt" "current_timestamp_dt" "timestamp_dt")
	echo ${colnames[$IDX]}
}

# bitmex is default database name
DATABASE=bitmex
HOSTNAME=localhost
PORT=3306

# True if we should include tradeBin1m (1 minute historical trade samples).
INCLUDE_1m_TRADE_BUCKETS=0

# Restrict the dump to the last day.
NDAYS=1

while getopts ":d:h:p:m:n:" opt; do
  case $opt in
    d)
      DATABASE=$OPTARG
      ;;
    h)
      HOSTNAME=$OPTARG
      ;;
    p)
      PORT=$OPTARG
      ;;
    m)
      INCLUDE_1m_TRADE_BUCKETS=$OPTARG
      ;;
    n)
      NDAYS=$OPTARG
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      cleanup 1
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      cleanup 1
      ;;
  esac
done

# Sanity-check value for option INCLUDE_1m_TRADE_BUCKETS.
if [ "${INCLUDE_1m_TRADE_BUCKETS}" != 0 -a "${INCLUDE_1m_TRADE_BUCKETS}" != 1 ]; then
	echo -e "Unrecognized value for option -m.  Allowable values are 0 and 1."
	cleanup 1
fi

NUM_RE='^[0-9]+$'
if [[ ! ${NDAYS} =~ ${NUM_RE} ]] ; then
	echo -e "Bad number of days."
	cleanup 1
elif [ ${NDAYS} -lt 1 ]; then
	echo -e "Number of days should 1 or greater."
	cleanup 1
fi

# Use mysqladmin to ping local instance of MySQL; otherwise, use nc. 
if [ "${HOSTNAME}" = "localhost" ]; then
	echo -e "[Enter password for MySQL root user...]"
	REACHABLE=`mysqladmin -h ${HOSTNAME} --port=${PORT} -u root -p ping`
	if [[ ! "${REACHABLE}" =~ "alive" ]]; then
		echo -e "MySQL instance not reachable at ${HOSTNAME} on port ${PORT}."
		cleanup 1
	fi
else
	REACHABLE=`eval nc -zv ${HOSTNAME} ${PORT}`
	if [[ ! "${REACHABLE}" =~ "succeeded" ]]; then
		echo -e "MySQL instance not reachable at ${HOSTNAME} on port ${PORT}."
		cleanup 1
	fi
fi

echo -e "[To read tables, enter password for MySQL user dbmasteruser...]"
MYSQL_TABLES=`mysql -h ${HOSTNAME} -B -u dbmasteruser -p ${DATABASE} -e "SHOW TABLES;"`
if [ -z "${MYSQL_TABLES}" ]; then
	echo -e "Could not determine tables.  Does the database \"${DATABASE}\" exist?"
	cleanup 1
fi

MYSQL_TABLES=`echo ${MYSQL_TABLES} | cut -d" " -f2-100 | tr '\n' ' '`
for tbl in ${MYSQL_TABLES}; do
	if [ "${tbl}" = "tradeBin1m" -a "${INCLUDE_1m_TRADE_BUCKETS}" = 0 ]; then
		continue
	fi
	datetime_column=`datetime_column ${tbl}`
	echo -e "[To dump table ${tbl}, enter password for MySQL user dbmasteruser...]"
	mysql -h ${HOSTNAME} -B -u dbmasteruser -p ${DATABASE} -e "SELECT * FROM ${tbl} WHERE ${datetime_column} >= (NOW() - interval ${NDAYS} day);" | tr '\t' ',' > ${TMPDIR}/${tbl}.csv
	if [ ! "${PIPESTATUS[0]}" = "0" ]; then
		echo -e "Could not dump table \"${tbl}\" from database \"${DATABASE}\"."
		cleanup 1
	fi
done

# Bundle all CSV files into a tarball with a filename derived from the hostname.
ZIPFILE=${DATABASE}-dump-`date +"%Y%m%d"`.zip
zip -j ${ZIPFILE} ${TMPDIR}/*.csv
echo -e "Done!  CSV files contain MySQL table dumps are bundled into the tarbarll ${ZIPFILE}!"

cleanup 0
