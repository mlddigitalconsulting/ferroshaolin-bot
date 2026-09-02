#!/usr/bin/ruby
# Comment-to-DM per @ferroshaolin — versione Ruby (zero dipendenze, gira
# con il Ruby di serie di macOS: niente da installare).
# Un passaggio per esecuzione, pensato per launchd ogni ~2 minuti:
#  1. legge gli ultimi post dell'account Instagram
#  2. cerca nei commenti nuovi le parole chiave delle regole di config.json
#     (la prima regola che combacia decide il DM da mandare)
#  3. manda la private reply (DM) e una risposta pubblica, ruotando tra
#     le varianti di public_replies per sembrare naturale
#  4. segna i commenti gestiti in state.json (mai doppioni)
require "net/http"
require "json"
require "time"
require "uri"

BASE  = File.expand_path(File.dirname(__FILE__))
GRAPH = "https://graph.facebook.com/v23.0"
LOG   = File.join(BASE, "bot.log")
STATE = File.join(BASE, "state.json")

def log(msg)
  line = "#{Time.now.strftime('%Y-%m-%d %H:%M:%S')}  #{msg}"
  puts line
  File.open(LOG, "a") { |f| f.puts line }
end

def load_env
  env = {}
  File.read(File.join(BASE, ".env")).each_line do |line|
    line = line.strip
    next if line.empty? || line.start_with?("#") || !line.include?("=")
    k, v = line.split("=", 2)
    env[k.strip] = v.strip
  end
  env
end

def api_get(path, params)
  uri = URI("#{GRAPH}/#{path}")
  uri.query = URI.encode_www_form(params)
  res = Net::HTTP.get_response(uri)
  body = JSON.parse(res.body)
  raise "API #{res.code}: #{body.dig('error', 'message')}" unless res.is_a?(Net::HTTPSuccess)
  body
end

def api_post(path, payload, token)
  uri = URI("#{GRAPH}/#{path}?#{URI.encode_www_form(access_token: token)}")
  req = Net::HTTP::Post.new(uri, "Content-Type" => "application/json")
  req.body = JSON.generate(payload)
  res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |h| h.request(req) }
  body = JSON.parse(res.body) rescue {}
  unless res.is_a?(Net::HTTPSuccess)
    err = body["error"] || {}
    raise "#{err['code']}/#{err['error_subcode']}: #{err['message']}"
  end
  body
end

def matches?(text, keywords)
  t = text.to_s.downcase
  keywords.any? { |k| t =~ /\b#{Regexp.escape(k.downcase)}\b/ }
end

env = load_env
cfg = JSON.parse(File.read(File.join(BASE, "config.json")))
%w[PAGE_ID PAGE_TOKEN IG_USER_ID].each do |k|
  abort "#{k} mancante nel .env" if env[k].to_s.empty?
end
abort "config.json senza 'rules'" unless cfg["rules"].is_a?(Array) && !cfg["rules"].empty?
token = env["PAGE_TOKEN"]
state = File.exist?(STATE) ? JSON.parse(File.read(STATE)) : {}
state["replied"]   ||= {}
state["reply_idx"] ||= 0

if state["own_username"].to_s.empty?
  me = api_get(env["IG_USER_ID"], { "fields" => "username", "access_token" => token })
  state["own_username"] = me["username"].to_s
end

cutoff  = Time.now.utc - cfg["max_comment_age_days"] * 86_400
handled = 0

begin
  media = api_get("#{env['IG_USER_ID']}/media", {
    "fields" => "id,timestamp", "limit" => cfg["media_limit"], "access_token" => token
  })["data"] || []

  media.each do |m|
    comments = api_get("#{m['id']}/comments", {
      "fields" => "id,text,timestamp,username", "limit" => 50, "access_token" => token
    })["data"] || []

    comments.each do |c|
      cid   = c["id"]
      entry = state["replied"][cid]
      next if entry && (entry["ok"] || entry["attempts"].to_i >= 3)
      next if c["username"].to_s == state["own_username"]
      next if Time.iso8601(c["timestamp"]) < cutoff
      rule = cfg["rules"].find { |r| matches?(c["text"], r["keywords"]) }
      next unless rule

      entry ||= { "attempts" => 0 }
      entry["attempts"] += 1
      begin
        api_post("#{env['PAGE_ID']}/messages", {
          "recipient" => { "comment_id" => cid },
          "message"   => { "text" => rule["dm_message"] },
        }, token)
        entry["ok"] = true
        log "DM inviato a @#{c['username']} [#{rule['keywords'].first}] (commento: #{c['text'].to_s[0, 60].inspect})"
        handled += 1
      rescue => e
        entry["error"] = e.message
        log "ERRORE DM a @#{c['username']}: #{e.message}"
      end

      replies = cfg["public_replies"] || []
      if entry["ok"] && !replies.empty?
        reply_text = replies[state["reply_idx"].to_i % replies.size]
        begin
          api_post("#{cid}/replies", { "message" => reply_text }, token)
          state["reply_idx"] = state["reply_idx"].to_i + 1
        rescue => e
          log "ERRORE risposta pubblica a @#{c['username']}: #{e.message}"
        end
      end

      state["replied"][cid] = entry
      File.write(STATE, JSON.pretty_generate(state))
      sleep 1
    end
  end

  # --- DM diretti: chi scrive "info"/"corso" in chat riceve la stessa risposta ---
  # Solo se la config lo abilita (dm_keywords_enabled), una volta per conversazione,
  # solo quando l'ULTIMO messaggio è dell'utente (così non risponde dove Ale sta già
  # scrivendo a mano) e contiene una parola chiave.
  if cfg["dm_keywords_enabled"]
   begin
    state["dm_replied"] ||= {}
    convos = api_get("#{env['IG_USER_ID']}/conversations", {
      "platform"     => "instagram",
      "fields"       => "id,messages.limit(5){id,from,message,created_time}",
      "limit"        => 20,
      "access_token" => token,
    })["data"] || []

    convos.each do |conv|
      msgs = (conv.dig("messages", "data") || []).sort_by { |m| m["created_time"].to_s }
      last = msgs.last
      next if last.nil?
      # l'ultimo messaggio deve essere dell'UTENTE, non nostro
      next if last.dig("from", "id").to_s == env["IG_USER_ID"].to_s
      sender = last.dig("from", "id").to_s
      next if sender.empty?
      next if state["dm_replied"][sender]

      rule = cfg["rules"].find { |r| matches?(last["message"], r["keywords"]) }
      next unless rule

      begin
        api_post("#{env['IG_USER_ID']}/messages", {
          "recipient" => { "id" => sender },
          "message"   => { "text" => rule["dm_message"] },
        }, token)
        state["dm_replied"][sender] = { "ok" => true, "rule" => rule["keywords"].first }
        log "Risposta DM a #{sender} [#{rule['keywords'].first}] (messaggio: #{last['message'].to_s[0, 60].inspect})"
        handled += 1
      rescue => e
        log "ERRORE risposta DM a #{sender}: #{e.message}"
      end
      File.write(STATE, JSON.pretty_generate(state))
      sleep 1
    end
   rescue => e
    # I DM richiedono l'App Review di Meta (accesso avanzato a
    # instagram_manage_messages). Finché non c'è, l'endpoint conversations
    # risponde "capability" (#3): lo registriamo una volta e NON blocchiamo
    # il resto del bot (i commenti funzionano comunque).
    log "DM non disponibili (serve App Review Meta): #{e.message}"
   end
  end

  File.write(STATE, JSON.pretty_generate(state))
  log "Passaggio completato: #{handled} invii" if handled > 0
rescue => e
  log "ERRORE: #{e.message}"
  exit 1
end
