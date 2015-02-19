'''Profiling runner.'''

import os
import subprocess
import time
import atexit


def main():
    server_proc = subprocess.Popen([
        'python3', '-m', 'huhhttp', '--port=8855', '--seed=4567',
        '--fuzz-period=999999'
    ])

    client_env = {
        'PYTHONPATH': os.path.join(
            os.path.abspath(os.path.dirname(__file__)), '..', '..'
        ),
        'RUN_PROFILE': '1',
    }

    client_proc = subprocess.Popen(
        [
            'python3', '-m', 'wpull', 'localhost:8855', '--waitretry=0',
            '--timeout=0.5', '-r',  '--page-requisites', '-l=4', '--tries=1',
            '--delete-after',
        ],
        env=client_env
    )

    def cleanup():
        if server_proc.returncode is None:
            try:
                server_proc.terminate()
            except OSError:
                pass
            time.sleep(0.1)

        if client_proc.returncode is None:
            try:
                client_proc.terminate()
            except OSError:
                pass
            time.sleep(0.1)

        try:
            server_proc.kill()
        except OSError:
            pass
        try:
            client_proc.kill()
        except OSError:
            pass

    atexit.register(cleanup)

    client_proc.wait()
    cleanup()


if __name__ == '__main__':
    main()
