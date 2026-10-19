"use strict";
// Exercise the actual inline Remote Display JavaScript with synthetic browser events.
// No real LCD, server or power switching is used.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync(0, "utf8");
const match = html.match(/<script>\s*([\s\S]*?)<\/script>/);
assert.ok(match, "Remote Display inline script must exist");

function viewer() {
  class Element {
    constructor(dataset = {}) {
      this.dataset = dataset;
      this.handlers = new Map();
      this.textContent = "";
    }
    addEventListener(type, handler) {
      const handlers = this.handlers.get(type) || [];
      handlers.push(handler);
      this.handlers.set(type, handlers);
    }
    fire(type, data = {}) {
      const e = {
        target: this, button: 0, pointerId: 1, pointerType: "mouse",
        preventDefault() { this.defaultPrevented = true; },
        ...data
      };
      for (const handler of this.handlers.get(type) || []) handler(e);
      return e;
    }
    setPointerCapture() {}
    closest() { return this === enter ? this : null; }
  }
  const view = new Element(), enter = new Element({kind:"press"});
  const ccw = new Element({kind:"rotate",value:"1"});
  const cw = new Element({kind:"rotate",value:"-1"});
  const screen = new Element(), status = new Element();
  const elements = {view, screen, status};
  const document = {
    getElementById: id => elements[id],
    querySelector: () => enter,
    querySelectorAll: () => [ccw, enter, cw],
    addEventListener() {},
    hidden: false
  };
  const window = {addEventListener() {}};
  const requests = [];
  const fetch = async (url, request) => {
    assert.equal(url, "/input");
    requests.push(JSON.parse(request.body));
    return {ok:true,status:202};
  };
  class Image { set src(value) { this._src = value; } }
  vm.runInNewContext(match[1], {document,window,fetch,Image,setTimeout() {}}, {timeout:1000});
  return {view,enter,requests};
}
async function settle() {
  for (let i = 0; i < 24; i++) await Promise.resolve();
}
function finger(id, x = 30, y = 20) {
  return {identifier:id,clientX:x,clientY:y};
}
function touches(el, type, ...touches) {
  return el.fire(type, {touches:type==="touchend"||type==="touchcancel"?[]:touches,
                        changedTouches:touches});
}
async function main() {
  // Android: long touch may cancel pointer capture; touchend still owns release.
  {
    const {view,enter,requests} = viewer(), t = finger(7);
    enter.fire("pointerdown", {pointerType:"touch"});
    touches(enter,"touchstart",t);
    await settle();
    enter.fire("pointercancel", {pointerType:"touch"});
    view.fire("pointercancel", {pointerType:"touch"});
    enter.fire("lostpointercapture", {pointerType:"touch"});
    view.fire("lostpointercapture", {pointerType:"touch"});
    touches(enter,"touchend",t);
    await settle();
    assert.deepEqual(requests, [{kind:"hold_start"},{kind:"hold_end"}]);
  }
  // Touch cancellation must never be converted into release/power-off.
  {
    const {enter,requests} = viewer(), t = finger(9);
    touches(enter,"touchstart",t);
    await settle();
    touches(enter,"touchcancel",t);
    touches(enter,"touchend",t);
    await settle();
    assert.deepEqual(requests, [{kind:"hold_start"},{kind:"hold_cancel"}]);
  }
  // Dragging the finger away cancels, even if the OS sends a later touchend.
  {
    const {enter,requests} = viewer(), t = finger(11);
    touches(enter,"touchstart",t);
    await settle();
    touches(enter,"touchmove",finger(11,90,20));
    touches(enter,"touchend",t);
    await settle();
    assert.deepEqual(requests, [{kind:"hold_start"},{kind:"hold_cancel"}]);
  }
  // Desktop pointer capture loss after a normal release cannot cancel twice.
  {
    const {enter,requests} = viewer();
    enter.fire("pointerdown", {pointerType:"mouse"});
    await settle();
    enter.fire("pointerup", {pointerType:"mouse"});
    enter.fire("lostpointercapture", {pointerType:"mouse"});
    await settle();
    assert.deepEqual(requests, [{kind:"hold_start"},{kind:"hold_end"}]);
  }
  // Keyboard autorepeat must not send multiple hold_start requests.
  {
    const {view,requests} = viewer();
    view.fire("keydown", {key:"Enter",repeat:false});
    view.fire("keydown", {key:"Enter",repeat:true});
    await settle();
    view.fire("keyup", {key:"Enter"});
    await settle();
    assert.deepEqual(requests, [{kind:"hold_start"},{kind:"hold_end"}]);
  }
  console.log("Mobile touch, pointer, cancellation, and keyboard gesture contracts OK");
}
main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
