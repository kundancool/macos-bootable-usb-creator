"""Supported target releases and Apple's published download links.

Direct DMG URLs are the links in https://support.apple.com/en-us/102662.
Availability is controlled by Apple. Mavericks has no direct download on that
page, so it requires an existing original full installer app.
"""
RELEASES = {
    'lion': {'version': '10.7', 'title': 'OS X Lion', 'app': 'Install Mac OS X Lion.app', 'method': 'restore',
             'url': 'https://updates.cdn-apple.com/2021/macos/041-7683-20210614-E610947E-C7CE-46EB-8860-D26D71F0D3EA/InstallMacOSX.dmg'},
    'mountain-lion': {'version': '10.8', 'title': 'OS X Mountain Lion', 'app': 'Install OS X Mountain Lion.app', 'method': 'restore',
                      'url': 'https://updates.cdn-apple.com/2021/macos/031-0627-20210614-90D11F33-1A65-42DD-BBEA-E1D9F43A6B3F/InstallMacOSX.dmg'},
    'mavericks': {'version': '10.9', 'title': 'OS X Mavericks', 'app': 'Install OS X Mavericks.app', 'method': 'createinstallmedia'},
    'yosemite': {'version': '10.10', 'title': 'OS X Yosemite', 'app': 'Install OS X Yosemite.app', 'method': 'createinstallmedia',
                 'url': 'https://updates-http.cdn-apple.com/2019/cert/061-41343-20191023-02465f92-3ab5-4c92-bfe2-b725447a070d/InstallMacOSX.dmg'},
    'el-capitan': {'version': '10.11', 'title': 'OS X El Capitan', 'app': 'Install OS X El Capitan.app', 'method': 'createinstallmedia',
                   'url': 'https://updates-http.cdn-apple.com/2019/cert/061-41424-20191024-218af9ec-cf50-4516-9011-228c78eda3d2/InstallMacOSX.dmg'},
    'sierra': {'version': '10.12', 'title': 'macOS Sierra', 'app': 'Install macOS Sierra.app', 'method': 'createinstallmedia',
               'url': 'https://updates-http.cdn-apple.com/2019/cert/061-39476-20191023-48f365f4-0015-4c41-9f44-39d3d2aca067/InstallOS.dmg'},
    'high-sierra': {'version': '10.13', 'title': 'macOS High Sierra', 'app': 'Install macOS High Sierra.app', 'method': 'createinstallmedia', 'catalog': True},
    'mojave': {'version': '10.14', 'title': 'macOS Mojave', 'app': 'Install macOS Mojave.app', 'method': 'createinstallmedia', 'catalog': True},
    'catalina': {'version': '10.15', 'title': 'macOS Catalina', 'app': 'Install macOS Catalina.app', 'method': 'createinstallmedia', 'catalog': True},
}


def normalize_release(value):
    value = value.lower().strip().replace(' ', '-')
    aliases = {release['version']: key for key, release in RELEASES.items()}
    aliases.update({'mountainlion': 'mountain-lion', 'elcapitan': 'el-capitan', 'highsierra': 'high-sierra'})
    key = aliases.get(value, value)
    if key not in RELEASES:
        raise ValueError('Choose a macOS release from Lion (10.7) through Catalina (10.15).')
    return key
