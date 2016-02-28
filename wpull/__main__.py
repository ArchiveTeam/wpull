# encoding=utf-8
import os
import time

import wpull.application.main


if __name__ == '__main__':
    if os.environ.get('RUN_PROFILE'):
        import cProfile
        cProfile.run('wpull.application.main()', 'stats-{0}.profile'.format(int(time.time())))
        # For Python 3.2, I suggest installing runsnakerun to view the
        # profile file graphically
        # For Python 3.4, use kcachegrind and pyprof2calltree, or
        # try snakeviz
    elif os.environ.get('RUN_PDB'):
        import pdb

        def wrapper():
            wpull.application.main.main(exit=False)
            pdb.set_trace()

        pdb.runcall(wrapper)
    else:
        wpull.application.main.main()
