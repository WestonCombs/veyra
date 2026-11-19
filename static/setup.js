"use strict";
const port=document.querySelector('meta[name="tls-port"]').content;
const link=document.getElementById("secure-link");
link.href=`https://${location.hostname}:${port}/join${location.hash}`;
