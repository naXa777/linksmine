# Maintainer: Pavel Homal <https://github.com/naXa777>
pkgname=linksmine
pkgver=1.0.0rc.1
pkgrel=1
pkgdesc='CLI setup wizard for Limine boot-entry restart shortcuts'
arch=('x86_64')
url='https://github.com/naXa777/linksmine'
license=('MIT')
depends=('python' 'sudo' 'systemd' 'e2fsprogs' 'kdialog')
makedepends=('make')
source=('linksmine' 'README.md' 'LICENSE' 'Makefile' 'test_core.py')
sha256sums=('67dc8880e53db0b7abb1797b73d8895bf3b91f98d45380ee8bdcd913af3052d5'
            '1bd7c078424a45577b7667ea7ee3e4a8335744f6763ebb80185c14861e633d9d'
            '4a5a3741555043ac7298b3bbcb3083f5bbd01dc5897310737ec6d5fce5485893'
            '9052e228bd3589879eca839d0a830a82e1d9397f0cdb5aacb167a1d7d265b3a0'
            '34cb6554f6f98fd66f3083b227bdf8c114382f0fd725f4373d1cf64a84b07d60')

check() {
    cd "$srcdir"
    python -m unittest -v test_core
}

package() {
    make -C "$srcdir" DESTDIR="$pkgdir" install
}
