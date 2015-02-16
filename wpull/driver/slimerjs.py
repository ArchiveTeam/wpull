'''SlimerJS'''
import os
import re
import subprocess
import tempfile

from wpull.driver.phantomjs import PhantomJSDriver


CERT_OVERRIDE_ENTRY = (
    'example.com:443	OID.2.16.840.1.101.3.4.2.1	'
    '48:11:D6:28:ED:03:3D:68:B1:06:E6:9D:CD:86:8B:CD:'
    'FF:0B:99:A9:7C:75:75:ED:E0:84:AC:F6:C2:72:E6:6D	'
    'MUT	'
    'AAAAAAAAAAAAAAAJAAAAUACrGmQcfHi3gDBOMQswCQYDVQQGEwJYWDERMA8GA1UE  '
    'CAwISW50ZXJuZXQxFDASBgNVBAoMC1dwdWxsLVByb3h5MRYwFAYDVQQDDA13cHVs  '
    'bC5pbnZhbGlk'
    '\n'
)


class SlimerJSDriver(PhantomJSDriver):
    def __init__(self, exe_path='slimerjs', extra_args=None, params=None,
                 root_dir='.'):
        self._profile_dir = tempfile.TemporaryDirectory(
            dir=root_dir, prefix='wpull-slimerjs'
        )

        extra_args = extra_args or []
        extra_args.extend(('-profile', self._profile_dir.name))

        self._write_cert_override_file()

        super().__init__(exe_path=exe_path, extra_args=extra_args, params=params)

    def _write_cert_override_file(self):
        filename = os.path.join(self._profile_dir.name, 'cert_override.txt')

        with open(filename, 'w') as cert_file:
            cert_file.write(CERT_OVERRIDE_ENTRY)

    def close(self):
        super().close()
        self._profile_dir.cleanup()


def get_version(exe_path='slimerjs'):
    process = subprocess.Popen(
        [exe_path, '--version'],
        stdout=subprocess.PIPE
    )
    version_string = process.communicate()[0]
    version_string = version_string.decode().strip()

    match = re.search(r'SlimerJS ([0-9a-zA-Z.]+),', version_string)

    if not match:
        raise ValueError('Could not find version string')

    version_string = match.group(1)

    assert ' ' not in version_string, version_string

    return version_string
