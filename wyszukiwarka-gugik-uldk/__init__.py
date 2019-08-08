def classFactory(iface):  # pylint: disable=invalid-name

    from .plugin import Plugin
    return Plugin(iface)
