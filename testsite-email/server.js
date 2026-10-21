// Minimal email-auth TARGET site. In-memory store; not for production.
const express = require('express');
const nodemailer = require('nodemailer');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const PORT = +process.env.PORT || 8890;
const BASE_URL = process.env.BASE_URL || `http://localhost:${PORT}`;
const transport = nodemailer.createTransport({
  host: process.env.SMTP_HOST || 'localhost',
  port: +process.env.SMTP_PORT || 1025,
  secure: false,
  ignoreTLS: true, // Mailpit default has no TLS
  connectionTimeout: 5000, greetingTimeout: 5000, socketTimeout: 10000,
});
const MAIL_FROM = process.env.MAIL_FROM || 'noreply@testsite.local';

const users = new Map();    // email -> {email, hash, salt, active, token, otp}
const sessions = new Map(); // sid -> email

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ESC[c]);
// Template contract: views/<name>.html with {{key}} placeholders (HTML-escaped).
function render(res, name, vars = {}, status = 200) {
  const html = fs.readFileSync(path.join(__dirname, 'views', name + '.html'), 'utf8')
    .replace(/\{\{(\w+)\}\}/g, (_, k) => esc(vars[k]));
  res.status(status).type('html').send(html);
}
const hash = (pw, salt) => crypto.scryptSync(pw, salt, 32).toString('hex');
const cookies = req => Object.fromEntries((req.headers.cookie || '').split(/;\s*/).filter(Boolean).map(c => c.split(/=(.*)/s).slice(0, 2)));
const current = req => sessions.get(cookies(req).sid);
const eq = (a, b) => a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
const validEmail = e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

app.get('/join', (req, res) => render(res, 'join'));
app.post('/join', async (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const password = String(req.body.password || '');
  if (!validEmail(email)) return render(res, 'join', { error: 'Enter a valid email address.', email }, 400);
  if (password.length < 8) return render(res, 'join', { error: 'Password must be at least 8 characters.', email }, 400);
  const existing = users.get(email);
  if (existing && existing.active) return render(res, 'join', { error: 'That email is already registered.', email }, 409);
  const salt = crypto.randomBytes(16).toString('hex');
  const user = { email, salt, hash: hash(password, salt), active: false,
    token: crypto.randomBytes(24).toString('hex'),
    otp: String(crypto.randomInt(0, 1e6)).padStart(6, '0') };
  const link = `${BASE_URL}/verify?token=${user.token}`;
  try {
    await transport.sendMail({
      from: MAIL_FROM, to: email, subject: 'Confirm your account',
      text: `Your verification code is ${user.otp}\n\nOr open this link: ${link}\n`,
      html: `<p>Your verification code is <b>${user.otp}</b></p><p>Or <a href="${link}">click here to verify</a>.</p>`,
    });
  } catch (e) {
    return render(res, 'join', { error: `Could not send verification email (SMTP unreachable: ${e.code || e.message}). Try again later.`, email }, 503);
  }
  users.set(email, user); // only stored once the mail was actually sent
  res.redirect(`/verify?email=${encodeURIComponent(email)}`);
});

app.get('/verify', (req, res) => {
  const { token, email } = req.query;
  if (!token) return render(res, 'verify', { email: email || '' });
  const user = [...users.values()].find(u => eq(u.token, String(token)));
  if (!user) return render(res, 'verify', { error: 'Invalid or expired verification link.' }, 400);
  user.active = true;
  render(res, 'verify', { message: 'Email verified. You can now sign in.', verified: 'true' });
});
app.post('/verify', (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const code = String(req.body.code || '').trim();
  const user = users.get(email);
  if (!user || !eq(user.otp, code)) return render(res, 'verify', { error: 'Invalid verification code.', email }, 400);
  user.active = true;
  render(res, 'verify', { message: 'Email verified. You can now sign in.', verified: 'true', email });
});

app.get('/signin', (req, res) => render(res, 'signin'));
app.post('/signin', (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const user = users.get(email);
  if (!user || !eq(user.hash, hash(String(req.body.password || ''), user.salt)))
    return render(res, 'signin', { error: 'Incorrect email or password.', email }, 401);
  if (!user.active)
    return render(res, 'signin', { error: 'Account not verified. Check your email for the verification link or code.', email }, 403);
  const sid = crypto.randomBytes(24).toString('hex');
  sessions.set(sid, email);
  res.cookie('sid', sid, { httpOnly: true, sameSite: 'lax', path: '/' });
  res.redirect('/profile');
});

app.get('/me', (req, res) => {
  const email = current(req);
  email ? res.json({ authenticated: true, email }) : res.status(401).json({ authenticated: false });
});
app.get('/profile', (req, res) => {
  const email = current(req);
  email ? render(res, 'profile', { email }) : res.redirect('/signin');
});
app.post('/signout', (req, res) => { sessions.delete(cookies(req).sid); res.clearCookie('sid'); res.redirect('/signin'); });

app.listen(PORT, () => console.log(`testsite-email on ${BASE_URL} (SMTP ${process.env.SMTP_HOST || 'localhost'}:${process.env.SMTP_PORT || 1025})`));
