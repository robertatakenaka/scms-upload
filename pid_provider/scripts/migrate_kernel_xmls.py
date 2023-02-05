from .. import tasks


"""
python manage.py runscript migrate_kernel_xmls \
    --script-args pids-tail-2.txt \
    "mongodb://192.168.1.19:27017/para_pid_provider" 1 website
"""
def run(pids_file_path, db_uri, user_id, files_storage_app_name):
    tasks.migrate_kernel_xmls.apply_async(
        args=(
            pids_file_path, db_uri, user_id, files_storage_app_name
        )
    )
