from importlib.metadata import version


def get_version() -> str:
	try:
		return version('1')
	except Exception:
		return 'Archinstall version not found'
