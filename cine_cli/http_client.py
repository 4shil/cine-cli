from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal, Dict, Optional

    from httpx import Response

import httpx
from deprecation import deprecated
from devgoldyutils import LoggerAdapter, Colours

from . import __version__
from .utils import hide_ip
from .logger import cine_cli_logger
from .errors import SiteMaybeBlockedError

__all__ = ("HTTPClient",)

class HTTPClient():
    def __init__(
        self, 
        headers: Optional[Dict[str, str]] = None, 
        timeout: int = 15, 
        hide_ip: bool = True
    ) -> None:
        self.hide_ip = hide_ip
        self.headers = headers or {}

        self.logger = LoggerAdapter(cine_cli_logger, prefix = self.__class__.__name__)

        self.__httpx_client = httpx.Client(
            timeout = timeout, 
            cookies = None
        )

        super().__init__()

    def request(
        self, 
        method: Literal["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"],
        url: str, 
        params: Optional[Dict[str, str]] = None, 
        headers: Optional[Dict[str, str]] = None, 
        include_default_headers: bool = False, 
        redirect: bool = False, 
        **kwargs
    ) -> Response:
        """Performs a request with httpx and returns `httpx.Response`."""
        if headers is None:
            headers = {}

        if include_default_headers is True:

            if headers.get("Referer") is None:
                headers.update({"Referer": url})

            headers.update(self.headers)

        try:
            self.logger.debug(
                Colours.ORANGE.apply(method.upper()) + f" -> {hide_ip(url, self.hide_ip)}"
            )

            response = self.__httpx_client.request(
                method = method, 
                url = url, 
                params = params, 
                headers = headers, 
                follow_redirects = redirect, 
                **kwargs
            )

            if response.is_error:
                self.logger.debug(
                    f"{method.upper()} request to '{response.url}' {Colours.RED.apply('failed!')} ({response})"
                )

            return response

        except httpx.ConnectError as e:
            # TODO: I think this needs improving. I see people are getting certificate errors that aren't being caught here.
            if "[SSL: CERTIFICATE_VERIFY_FAILED]" in str(e):
                raise SiteMaybeBlockedError(url, e)

            raise e

    @deprecated(
        deprecated_in = "4.4", 
        current_version = __version__, 
        details = "Switch to 'HTTPClient.request()' for the latest functionality."
    )
    def get(
        self, 
        url: str, 
        headers: Dict[str, str] = {}, 
        include_default_headers: bool = True, 
        redirect: bool = False, 
        **kwargs
    ) -> Response:
        """Performs a GET request and returns httpx.Response."""
        return self.request(
            "GET", 
            url = url, 
            headers = headers, 
            include_default_headers = include_default_headers, 
            redirect = redirect,
            **kwargs
        )

    @deprecated(
        deprecated_in = "4.4", 
        current_version = __version__, 
        details = "Switch to 'HTTPClient.request()' for the latest functionality."
    )
    def post(
        self, 
        url: str,
        data: dict = {},
        json: dict = {}, 
        headers: dict = {}, 
        include_default_headers: bool = True, 
        redirect: bool = False, 
        **kwargs
    ) -> Response:
        """Performs a POST request and returns httpx.Response."""

        return self.request(
            "POST", 
            url = url, 
            data = data, 
            json = json, 
            headers = headers, 
            include_default_headers = include_default_headers, 
            redirect = redirect,
            **kwargs
        )

    def set_cookies(self, cookies: dict) -> None:
        """Sets cookies."""
        self.__httpx_client.cookies = cookies