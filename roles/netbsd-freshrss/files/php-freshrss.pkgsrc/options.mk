# $NetBSD$

PKG_OPTIONS_VAR=	PKG_OPTIONS.php-freshrss
PKG_SUPPORTED_OPTIONS=	mysql pgsql sqlite
PKG_SUGGESTED_OPTIONS=	pgsql

.include "../../mk/bsd.options.mk"

.if !empty(PKG_OPTIONS:Mmysql)
DEPENDS+=	${PHP_PKG_PREFIX}-pdo_mysql>=${PHP_BASE_VERS}:../../databases/php-pdo_mysql
.endif

.if !empty(PKG_OPTIONS:Mpgsql)
DEPENDS+=	${PHP_PKG_PREFIX}-pdo_pgsql>=${PHP_BASE_VERS}:../../databases/php-pdo_pgsql
.endif

.if !empty(PKG_OPTIONS:Msqlite)
DEPENDS+=	${PHP_PKG_PREFIX}-pdo_sqlite>=${PHP_BASE_VERS}:../../databases/php-pdo_sqlite
.endif
