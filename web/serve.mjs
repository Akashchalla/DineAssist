// Local preview with the same chat handler used on Vercel. No credentials required for table answers.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import handler from '../api/chat.js';
const root=path.resolve('dist');
http.createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/api/chat'){
  let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>24000){res.writeHead(413);res.end();return}}
  req.body=body;res.status=n=>{res.statusCode=n;return res};res.json=value=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));return res};
  await handler(req,res);return;
 }
 let filename;try{filename=path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname))}catch{res.writeHead(400);res.end();return}
 if(!filename.startsWith(root+path.sep)){res.writeHead(403);res.end();return}
 try{const data=await readFile(filename);const mime={'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css','.mp4':'video/mp4','.woff2':'font/woff2'};res.setHeader('Content-Type',mime[path.extname(filename)]||'application/octet-stream');res.end(data)}catch{res.writeHead(404);res.end('Not found')}
}).listen(4174,'127.0.0.1',()=>console.log('DineAssist preview: http://127.0.0.1:4174'));
