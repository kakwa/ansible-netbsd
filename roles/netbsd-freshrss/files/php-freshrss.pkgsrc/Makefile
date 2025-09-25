# $NetBSD: Makefile,v 1.1 2025/09/25 00:00:00 carpenti Exp $

ACCEPTABLE_LICENSES+= gnu-agpl-v3

FRESHRSS_VERSION=	1.27.0
DISTNAME=	FreshRSS-${FRESHRSS_VERSION}
PKGNAME=	${PHP_PKG_PREFIX}-freshrss-${FRESHRSS_VERSION}
PKGREVISION=	1
CATEGORIES=	www
MASTER_SITES=	-https://github.com/FreshRSS/FreshRSS/archive/${FRESHRSS_VERSION}.tar.gz
WRKSRC=		${WRKDIR}/FreshRSS-${FRESHRSS_VERSION}
MAINTAINER=	carpentier.pf@gmail.com
HOMEPAGE=	https://freshrss.org/
COMMENT=	FreshRSS is a self-hosted RSS feed aggregator
LICENSE=	gnu-agpl-v3

DEPENDS+=	${PHP_PKG_PREFIX}-mbstring>=${PHP_BASE_VERS}:../../converters/php-mbstring
DEPENDS+=	${PHP_PKG_PREFIX}-iconv>=${PHP_BASE_VERS}:../../converters/php-iconv
DEPENDS+=	${PHP_PKG_PREFIX}-curl>=${PHP_BASE_VERS}:../../www/php-curl
DEPENDS+=	${PHP_PKG_PREFIX}-intl>=${PHP_BASE_VERS}:../../textproc/php-intl
DEPENDS+=	${PHP_PKG_PREFIX}-pdo_pgsql>=${PHP_BASE_VERS}:../../databases/php-pdo_pgsql
DEPENDS+=	${PHP_PKG_PREFIX}-pdo_mysql>=${PHP_BASE_VERS}:../../databases/php-pdo_mysql
DEPENDS+=	${PHP_PKG_PREFIX}-pdo_sqlite>=${PHP_BASE_VERS}:../../databases/php-pdo_sqlite
DEPENDS+=	${PHP_PKG_PREFIX}-zip>=${PHP_BASE_VERS}:../../archivers/php-zip

.include "options.mk"

USE_PKGLOCALEDIR=	yes
USE_LANGUAGES=		# none

NO_BUILD=	yes

USE_TOOLS+=	pax

FRESHRSS_DIR=	share/freshrss
INSTALLATION_DIRS=	${FRESHRSS_DIR}

CHECK_INTERPRETER_SKIP+=	share/freshrss/cli/*.php
CHECK_INTERPRETER_SKIP+=	share/freshrss/app/install.php
CHECK_INTERPRETER_SKIP+=	share/freshrss/app/actualize_script.php

.include "../../mk/bsd.prefs.mk"

APACHE_USER?=	www
APACHE_GROUP?=	www
PKG_GROUPS=	${APACHE_GROUP}
PKG_USERS=	${APACHE_USER}:${APACHE_GROUP}

PKG_USERS_VARS=		APACHE_USER
PKG_GROUPS_VARS=	APACHE_GROUP

FILES_SUBST+=	WWWGRP=${APACHE_GROUP} WWWOWN=${APACHE_USER} \
		FRESHRSS_DIR=${FRESHRSS_DIR}

CONF_FILES_PERMS=	${PREFIX}/share/freshrss/config.default.php \
			${PREFIX}/share/freshrss/config.php \
			${APACHE_USER} ${APACHE_GROUP} 640

do-install:
	cd ${WRKSRC} && pax -rw -pmp * \
		${DESTDIR}${PREFIX}/share/freshrss

.include "../../lang/php/json.mk"
.include "../../mk/bsd.pkg.mk"
