import sys, json, os, traceback
import importlib.util, importlib.machinery
from datetime import datetime

LOG_PATH = '/tmp/reality-converter-validation.log'


def _log(message):
    try:
        with open(LOG_PATH, 'a') as log_file:
            log_file.write('%s %s\n' % (datetime.now().isoformat(), message))
    except:
        pass


def main(args):
    execpath = os.path.split(__file__)[0]
    if execpath not in sys.path:
        sys.path.insert(0, execpath)
    import usd_bootstrap
    _log('validate args=%r cwd=%r' % (args, os.getcwd()))

    usd_args = [
        arg for arg in args
        if os.path.splitext(arg)[1].lower() in ('.usd', '.usda', '.usdc', '.usdz')
    ]
    if not usd_args:
        _log('skip non-USD inputs')
        return 0

    errors = []
    out = 0
    try:
        _ldr = importlib.machinery.SourceFileLoader(
            'usdARKitChecker', os.path.join(execpath, 'usdARKitChecker'))
        _spec = importlib.util.spec_from_loader('usdARKitChecker', _ldr)
        usdARKitChecker = importlib.util.module_from_spec(_spec)
        _ldr.exec_module(usdARKitChecker)
        # Supress output from usdARKitChecker
        sys.stdout = open(os.devnull, 'w')
        out = usdARKitChecker.main(usd_args, errors)
        # Enable output from realityConvertChecker
        sys.stdout = sys.__stdout__
    except Exception:
        sys.stdout = sys.__stdout__
        _log('exception:\n%s' % traceback.format_exc())
        print(json.dumps([{
            'file': args[0] if args else '',
            'errors': [{'code': 'ERR_CHECKER_CRASH'}]
        }]))
        return 1

    # Drop empty error buckets after filtering
    errors = [e for e in errors if e.get('errors')]
    _log('exit=%s errors=%s' % (out, json.dumps(errors)))

    if out != 0 and len(errors) > 0:
        print(json.dumps(errors))
        return 1
    return 0

if __name__ == '__main__':
    argumentList = sys.argv[1:]
    sys.exit(main(argumentList))