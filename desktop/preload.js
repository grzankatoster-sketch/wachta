"use strict";

/**
 * The only bridge between the status page and the main process.
 *
 * Deliberately three functions wide. The status page is the one screen that runs before anything
 * has been checked, so it is also the one screen an attacker would most like to reach; it gets a
 * channel to listen on and a button to press, and no access to Node.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("wachta", {
  naKrok: (oddzwon) => ipcRenderer.on("wachta:krok", (_zdarzenie, dane) => oddzwon(dane)),
  ponow: () => ipcRenderer.invoke("wachta:ponow"),
  ostatniBlad: () => ipcRenderer.invoke("wachta:blad"),
});
