#!/usr/bin/env node

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadSignupScript() {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  const matches = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.ok(matches.length > 0, 'expected at least one inline script in index.html');
  return matches[matches.length - 1][1];
}

function createElement(id) {
  return {
    id,
    style: { display: '' },
    disabled: false,
    textContent: '',
  };
}

function createEnvironment(fetchImpl) {
  const listeners = new Map();
  const signupForm = createElement('signupForm');
  const signupButton = createElement('signupButton');
  const signupSuccess = createElement('signupSuccess');
  const signupError = createElement('signupError');
  const signupNote = createElement('signupNote');

  signupForm.action = 'https://formspree.io/f/mreywkbd';
  signupForm.submitCount = 0;
  signupForm.submit = function submit() {
    signupForm.submitCount += 1;
  };
  signupForm.querySelector = function querySelector(selector) {
    assert.equal(selector, 'button');
    return signupButton;
  };
  signupForm.addEventListener = function addEventListener(type, listener) {
    listeners.set(type, listener);
  };

  const document = {
    getElementById(id) {
      switch (id) {
        case 'signupForm':
          return signupForm;
        case 'signupSuccess':
          return signupSuccess;
        case 'signupError':
          return signupError;
        default:
          return null;
      }
    },
    querySelector(selector) {
      assert.equal(selector, '.signup-note');
      return signupNote;
    },
  };

  class FakeFormData {
    constructor(form) {
      this.form = form;
    }
  }

  const context = {
    document,
    window: {
      fetch: fetchImpl,
      FormData: FakeFormData,
      matchMedia: function matchMedia() {
        return { matches: true };
      },
    },
    fetch: fetchImpl,
    FormData: FakeFormData,
    console,
    setTimeout,
    clearTimeout,
  };

  vm.runInNewContext(loadSignupScript(), context, { filename: 'index.html:inline-signup-script' });

  async function submit() {
    const listener = listeners.get('submit');
    assert.ok(listener, 'expected signup submit listener to be registered');
    const event = {
      defaultPrevented: false,
      preventDefault() {
        this.defaultPrevented = true;
      },
    };
    await listener(event);
    return event;
  }

  return {
    submit,
    signupForm,
    signupButton,
    signupSuccess,
    signupError,
    signupNote,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function testSuccessPath() {
  const pending = deferred();
  const fetchCalls = [];
  const env = createEnvironment((url, options) => {
    fetchCalls.push({ url, options });
    return pending.promise;
  });

  const firstSubmitPromise = env.submit();
  await Promise.resolve();

  assert.equal(fetchCalls.length, 1, 'first submit should start one request');
  assert.equal(env.signupButton.disabled, true, 'button should be disabled while request is in flight');

  const secondEvent = await env.submit();
  assert.equal(secondEvent.defaultPrevented, true, 'duplicate submit should still be intercepted');
  assert.equal(fetchCalls.length, 1, 'duplicate submit should not start another request while disabled');

  pending.resolve({ ok: true });
  const firstEvent = await firstSubmitPromise;
  assert.equal(firstEvent.defaultPrevented, true, 'enhanced submit should prevent default submission');
  assert.equal(env.signupForm.style.display, 'none', 'success should hide the form');
  assert.equal(env.signupSuccess.style.display, 'block', 'success should show confirmation');
  assert.equal(env.signupNote.style.display, 'none', 'success should hide the note');
}

async function testNonOkResponse() {
  const env = createEnvironment(async () => ({ ok: false }));

  const event = await env.submit();

  assert.equal(event.defaultPrevented, true, 'non-OK response path should prevent default submit');
  assert.equal(env.signupError.style.display, 'block', 'non-OK response should show inline error');
  assert.equal(env.signupButton.disabled, false, 'non-OK response should re-enable the button');
  assert.equal(env.signupForm.submitCount, 0, 'non-OK response should not fall back to native submit');
}

async function testThrownFailureFallsBackToNativeSubmit() {
  const env = createEnvironment(async () => {
    throw new Error('network failed');
  });

  const event = await env.submit();

  assert.equal(event.defaultPrevented, true, 'fallback path still intercepts enhanced submit');
  assert.equal(env.signupButton.disabled, false, 'fallback path should re-enable the button');
  assert.equal(env.signupForm.submitCount, 1, 'thrown failure should fall back to signupForm.submit()');
}

async function main() {
  await testSuccessPath();
  await testNonOkResponse();
  await testThrownFailureFallsBackToNativeSubmit();
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
