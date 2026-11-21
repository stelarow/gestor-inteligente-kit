package main

import (
	"context"
	"database/sql"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"reflect"
	"strings"
	"syscall"
	"time"

	_ "github.com/mattn/go-sqlite3"
	"github.com/mdp/qrterminal"

	"bytes"

	"go.mau.fi/whatsmeow"
	waProto "go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"
)

// Message represents a chat message for our client
type Message struct {
	Time      time.Time
	Sender    string
	Content   string
	IsFromMe  bool
	MediaType string
	Filename  string
}

// Database handler for storing message history
type MessageStore struct {
	db *sql.DB
}

// Initialize message store
func NewMessageStore() (*MessageStore, error) {
	// Create directory for database if it doesn't exist
	if err := os.MkdirAll("store", 0755); err != nil {
		return nil, fmt.Errorf("failed to create store directory: %v", err)
	}

	// Open SQLite database for messages
	db, err := sql.Open("sqlite3", "file:store/messages.db?_foreign_keys=on")
	if err != nil {
		return nil, fmt.Errorf("failed to open message database: %v", err)
	}

	// Create tables if they don't exist
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS chats (
			jid TEXT PRIMARY KEY,
			name TEXT,
			last_message_time TIMESTAMP
		);
		
		CREATE TABLE IF NOT EXISTS messages (
			id TEXT,
			chat_jid TEXT,
			sender TEXT,
			content TEXT,
			timestamp TIMESTAMP,
			is_from_me BOOLEAN,
			media_type TEXT,
			filename TEXT,
			url TEXT,
			media_key BLOB,
			file_sha256 BLOB,
			file_enc_sha256 BLOB,
			file_length INTEGER,
			PRIMARY KEY (id, chat_jid),
			FOREIGN KEY (chat_jid) REFERENCES chats(jid)
		);

		CREATE TABLE IF NOT EXISTS ad_clicks (
			message_id TEXT,
			chat_jid TEXT,
			sender TEXT,
			ctwa_clid TEXT,
			source_id TEXT,
			source_type TEXT,
			source_url TEXT,
			title TEXT,
			timestamp TIMESTAMP,
			PRIMARY KEY (message_id, chat_jid)
		);
	`)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to create tables: %v", err)
	}

	return &MessageStore{db: db}, nil
}

// Close the database connection
func (store *MessageStore) Close() error {
	return store.db.Close()
}

// Store a chat in the database
func (store *MessageStore) StoreChat(jid, name string, lastMessageTime time.Time) error {
	_, err := store.db.Exec(
		"INSERT OR REPLACE INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
		jid, name, lastMessageTime,
	)
	return err
}

// HasMessage reports whether this WhatsApp message id is already in the local store.
// Used to avoid re-firing the router webhook when whatsmeow re-emits the same event
// (INSERT OR REPLACE would otherwise "succeed" and postIncomingWebhook would run again).
func (store *MessageStore) HasMessage(id string) (bool, error) {
	if id == "" {
		return false, nil
	}
	var n int
	err := store.db.QueryRow(`SELECT COUNT(1) FROM messages WHERE id = ?`, id).Scan(&n)
	if err != nil {
		return false, err
	}
	return n > 0, nil
}

// GetMessageContentByID looks up a previously stored message body (for quote fallback).
// Prefer exact chat_jid match; if empty or miss, fall back to id-only (same WA id is unique enough in practice).
func (store *MessageStore) GetMessageContentByID(id, chatJID string) (string, error) {
	if store == nil || id == "" {
		return "", nil
	}
	var content sql.NullString
	var mediaType sql.NullString
	var err error
	if chatJID != "" {
		err = store.db.QueryRow(
			`SELECT content, media_type FROM messages WHERE id = ? AND chat_jid = ? LIMIT 1`,
			id, chatJID,
		).Scan(&content, &mediaType)
		if err == sql.ErrNoRows {
			err = store.db.QueryRow(
				`SELECT content, media_type FROM messages WHERE id = ? LIMIT 1`,
				id,
			).Scan(&content, &mediaType)
		}
	} else {
		err = store.db.QueryRow(
			`SELECT content, media_type FROM messages WHERE id = ? LIMIT 1`,
			id,
		).Scan(&content, &mediaType)
	}
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	body := strings.TrimSpace(content.String)
	media := strings.TrimSpace(mediaType.String)
	if body != "" {
		return body, nil
	}
	if media != "" {
		return "[" + media + "]", nil
	}
	return "", nil
}

// Store a message in the database
func (store *MessageStore) StoreMessage(id, chatJID, sender, content string, timestamp time.Time, isFromMe bool,
	mediaType, filename, url string, mediaKey, fileSHA256, fileEncSHA256 []byte, fileLength uint64) error {
	// Only store if there's actual content or media
	if content == "" && mediaType == "" {
		return nil
	}

	_, err := store.db.Exec(
		`INSERT OR REPLACE INTO messages 
		(id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename, url, media_key, file_sha256, file_enc_sha256, file_length) 
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, chatJID, sender, content, timestamp, isFromMe, mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength,
	)
	return err
}

// StoreAdClick keeps the Click-to-WhatsApp ids (ctwa_clid + ad id) that formatAdContext
// leaves out of the message text. the router can send them back to Meta when
// the contact buys, so the sale is credited to the right ad.
func (store *MessageStore) StoreAdClick(id, chatJID, sender string, ad *waProto.ContextInfo_ExternalAdReplyInfo, timestamp time.Time) error {
	clid := strings.TrimSpace(ad.GetCtwaClid())
	sourceID := strings.TrimSpace(ad.GetSourceID())
	if clid == "" && sourceID == "" {
		return nil
	}
	_, err := store.db.Exec(
		`INSERT OR IGNORE INTO ad_clicks
		(message_id, chat_jid, sender, ctwa_clid, source_id, source_type, source_url, title, timestamp)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, chatJID, sender, clid, sourceID, strings.TrimSpace(ad.GetSourceType()),
		strings.TrimSpace(ad.GetSourceURL()), strings.TrimSpace(ad.GetTitle()), timestamp,
	)
	return err
}

// Get messages from a chat
func (store *MessageStore) GetMessages(chatJID string, limit int) ([]Message, error) {
	rows, err := store.db.Query(
		"SELECT sender, content, timestamp, is_from_me, media_type, filename FROM messages WHERE chat_jid = ? ORDER BY timestamp DESC LIMIT ?",
		chatJID, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var messages []Message
	for rows.Next() {
		var msg Message
		var timestamp time.Time
		err := rows.Scan(&msg.Sender, &msg.Content, &timestamp, &msg.IsFromMe, &msg.MediaType, &msg.Filename)
		if err != nil {
			return nil, err
		}
		msg.Time = timestamp
		messages = append(messages, msg)
	}

	return messages, nil
}

// Get all chats
func (store *MessageStore) GetChats() (map[string]time.Time, error) {
	rows, err := store.db.Query("SELECT jid, last_message_time FROM chats ORDER BY last_message_time DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	chats := make(map[string]time.Time)
	for rows.Next() {
		var jid string
		var lastMessageTime time.Time
		err := rows.Scan(&jid, &lastMessageTime)
		if err != nil {
			return nil, err
		}
		chats[jid] = lastMessageTime
	}

	return chats, nil
}

// truncateRunes trims s to at most max runes (safe for UTF-8 / emoji).
func truncateRunes(s string, max int) string {
	if max <= 0 || s == "" {
		return s
	}
	r := []rune(s)
	if len(r) <= max {
		return s
	}
	return string(r[:max]) + "…"
}

// formatAdContext pulls Instagram/CTWA Click-to-WhatsApp metadata that WhatsApp
// otherwise drops. The icebreaker text is often just "Olá! Posso ter mais
// informações sobre isso?" — the product lives in ExternalAdReply / link preview.
// Returned as a single line: [anúncio: Title — body | url | source]
func formatAdContext(msg *waProto.Message) string {
	if msg == nil {
		return ""
	}
	title, body, url, source := "", "", "", ""

	if ext := msg.GetExtendedTextMessage(); ext != nil {
		title = strings.TrimSpace(ext.GetTitle())
		body = strings.TrimSpace(ext.GetDescription())
		if mt := strings.TrimSpace(ext.GetMatchedText()); strings.HasPrefix(strings.ToLower(mt), "http") {
			url = mt
		}
	}

	if ci := getContextInfo(msg); ci != nil {
		if ad := ci.GetExternalAdReply(); ad != nil {
			if t := strings.TrimSpace(ad.GetTitle()); t != "" {
				title = t
			}
			if b := strings.TrimSpace(ad.GetBody()); b != "" {
				body = b
			}
			if u := strings.TrimSpace(ad.GetSourceURL()); u != "" {
				url = u
			}
			if app := strings.TrimSpace(ad.GetSourceApp()); app != "" {
				source = app
			}
		}
		if qad := ci.GetQuotedAd(); qad != nil {
			if c := strings.TrimSpace(qad.GetCaption()); c != "" && title == "" {
				title = c
			}
			if n := strings.TrimSpace(qad.GetAdvertiserName()); n != "" && source == "" {
				source = n
			}
		}
		if src := strings.TrimSpace(ci.GetEntryPointConversionSource()); src != "" && source == "" {
			source = src
		}
		if extSrc := strings.TrimSpace(ci.GetEntryPointConversionExternalSource()); extSrc != "" && source == "" {
			source = extSrc
		}
		if app := strings.TrimSpace(ci.GetEntryPointConversionApp()); app != "" && source == "" {
			source = app
		}
		if conv := strings.TrimSpace(ci.GetConversionSource()); conv != "" && source == "" {
			source = conv
		}
		if utm := ci.GetUtm(); utm != nil {
			if camp := strings.TrimSpace(utm.GetUtmCampaign()); camp != "" && title == "" {
				title = camp
			}
			if src := strings.TrimSpace(utm.GetUtmSource()); src != "" && source == "" {
				source = src
			}
		}
	}

	if title == "" && body == "" && url == "" && source == "" {
		return ""
	}
	// WhatsApp Status reply source=status, no CTWA title.
	// Do NOT emit "[anúncio: status]" — that triggers Instagram icebreaker and
	// the agent asks "which product?" while the flyer is in the quoted image.
	if title == "" && body == "" && url == "" && isStatusSourceLabel(source) {
		return "[status do WhatsApp]"
	}
	parts := make([]string, 0, 3)
	if title != "" {
		parts = append(parts, title)
	}
	if body != "" && !strings.EqualFold(body, title) {
		parts = append(parts, body)
	}
	head := strings.Join(parts, " — ")
	extra := make([]string, 0, 2)
	if url != "" {
		extra = append(extra, url)
	}
	if source != "" {
		extra = append(extra, source)
	}
	s := "[anúncio"
	if head != "" {
		s += ": " + head
	}
	if len(extra) > 0 {
		if head != "" {
			s += " | "
		} else {
			s += ": "
		}
		s += strings.Join(extra, " | ")
	}
	s += "]"
	return s
}

// extractPlainText returns the user-visible body of a message (no quote annotation).
// Includes Conversation, ExtendedText, and media captions.
func extractPlainText(msg *waProto.Message) string {
	if msg == nil {
		return ""
	}
	if text := msg.GetConversation(); text != "" {
		return text
	}
	if extendedText := msg.GetExtendedTextMessage(); extendedText != nil {
		if t := extendedText.GetText(); t != "" {
			return t
		}
	}
	if img := msg.GetImageMessage(); img != nil {
		if c := img.GetCaption(); c != "" {
			return c
		}
	}
	if vid := msg.GetVideoMessage(); vid != nil {
		if c := vid.GetCaption(); c != "" {
			return c
		}
	}
	if doc := msg.GetDocumentMessage(); doc != nil {
		if c := doc.GetCaption(); c != "" {
			return c
		}
	}
	if btn := msg.GetButtonsResponseMessage(); btn != nil {
		if t := btn.GetSelectedDisplayText(); t != "" {
			return t
		}
	}
	if lresp := msg.GetListResponseMessage(); lresp != nil {
		if t := lresp.GetTitle(); t != "" {
			return t
		}
		if s := lresp.GetSingleSelectReply(); s != nil {
			if t := s.GetSelectedRowID(); t != "" {
				return t
			}
		}
	}
	if tresp := msg.GetTemplateButtonReplyMessage(); tresp != nil {
		if t := tresp.GetSelectedDisplayText(); t != "" {
			return t
		}
	}
	// Shared contact card (vCard) — surface name + phone for the agent
	if c := msg.GetContactMessage(); c != nil {
		return formatSharedContact(c.GetDisplayName(), c.GetVcard())
	}
	return ""
}

// formatSharedContact builds agent-readable text from a WhatsApp contact share.
func formatSharedContact(displayName, vcard string) string {
	name := strings.TrimSpace(displayName)
	if name == "" {
		// FN: line in vCard
		for _, line := range strings.Split(vcard, "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(strings.ToUpper(line), "FN:") {
				name = strings.TrimSpace(line[3:])
				break
			}
		}
	}
	phone := extractPhoneFromVcard(vcard)
	parts := []string{"[contato compartilhado]"}
	if name != "" {
		parts = append(parts, "Nome: "+name)
	}
	if phone != "" {
		parts = append(parts, "Telefone: "+phone)
	}
	if len(parts) == 1 && strings.TrimSpace(vcard) != "" {
		// Fallback: keep a short vCard snippet so the agent still sees something
		snip := strings.Join(strings.Fields(vcard), " ")
		if len(snip) > 280 {
			snip = snip[:280] + "…"
		}
		parts = append(parts, snip)
	}
	return strings.Join(parts, "\n")
}

// extractPhoneFromVcard prefers TEL;waid=… then any TEL line.
func extractPhoneFromVcard(vcard string) string {
	if strings.TrimSpace(vcard) == "" {
		return ""
	}
	// waid is usually digits only (E.164 without +)
	lower := vcard
	for _, line := range strings.Split(lower, "\n") {
		line = strings.TrimSpace(line)
		up := strings.ToUpper(line)
		if strings.Contains(up, "WAID=") {
			// e.g. TEL;type=CELL;waid=5500000000000:+55 00 00000-0000
			idx := strings.Index(strings.ToLower(line), "waid=")
			if idx >= 0 {
				rest := line[idx+5:]
				// stop at : or ; or end
				end := len(rest)
				for i, ch := range rest {
					if ch == ':' || ch == ';' {
						end = i
						break
					}
				}
				digits := keepDigits(rest[:end])
				if len(digits) >= 10 {
					return digits
				}
			}
		}
	}
	for _, line := range strings.Split(vcard, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(strings.ToUpper(line), "TEL") {
			// take part after last :
			if i := strings.LastIndex(line, ":"); i >= 0 {
				digits := keepDigits(line[i+1:])
				if len(digits) >= 10 {
					return digits
				}
			}
		}
	}
	return ""
}

func keepDigits(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}

// getContextInfo returns WhatsApp reply/quote metadata if present on the message type.
func getContextInfo(msg *waProto.Message) *waProto.ContextInfo {
	if msg == nil {
		return nil
	}
	if ext := msg.GetExtendedTextMessage(); ext != nil {
		return ext.GetContextInfo()
	}
	if img := msg.GetImageMessage(); img != nil {
		return img.GetContextInfo()
	}
	if vid := msg.GetVideoMessage(); vid != nil {
		return vid.GetContextInfo()
	}
	if aud := msg.GetAudioMessage(); aud != nil {
		return aud.GetContextInfo()
	}
	if doc := msg.GetDocumentMessage(); doc != nil {
		return doc.GetContextInfo()
	}
	if stick := msg.GetStickerMessage(); stick != nil {
		return stick.GetContextInfo()
	}
	if btn := msg.GetButtonsResponseMessage(); btn != nil {
		return btn.GetContextInfo()
	}
	if lresp := msg.GetListResponseMessage(); lresp != nil {
		return lresp.GetContextInfo()
	}
	if tresp := msg.GetTemplateButtonReplyMessage(); tresp != nil {
		return tresp.GetContextInfo()
	}
	if loc := msg.GetLocationMessage(); loc != nil {
		return loc.GetContextInfo()
	}
	if c := msg.GetContactMessage(); c != nil {
		return c.GetContextInfo()
	}
	return nil
}

// isStatusSourceLabel is true for WhatsApp Status conversion sources, not Instagram/CTWA.
func isStatusSourceLabel(source string) bool {
	s := strings.ToLower(strings.TrimSpace(source))
	if s == "" {
		return false
	}
	if strings.Contains(s, "instagram") || strings.Contains(s, "facebook") || strings.Contains(s, "ctwa") {
		return false
	}
	return s == "status" || strings.HasPrefix(s, "status_") || s == "wa_status" || s == "whatsapp_status"
}

// isStatusQuote detects a reply to a WhatsApp Status (flyer, etc.).
func isStatusQuote(ci *waProto.ContextInfo) bool {
	if ci == nil {
		return false
	}
	rj := strings.ToLower(strings.TrimSpace(ci.GetRemoteJID()))
	if strings.Contains(rj, "status@broadcast") {
		return true
	}
	if strings.TrimSpace(ci.GetPosterStatusID()) != "" {
		return true
	}
	if ci.StatusAttributionType != nil || ci.StatusSourceType != nil || ci.GetIsGroupStatus() {
		return true
	}
	if len(ci.GetStatusAttributions()) > 0 {
		return true
	}
	if isStatusSourceLabel(ci.GetEntryPointConversionSource()) {
		return true
	}
	if isStatusSourceLabel(ci.GetConversionSource()) {
		return true
	}
	return false
}

// formatQuotedSnippet builds a short, agent-readable preview of a quoted message.
// Does not recurse into nested quotes (keeps storage/webhook small).
func formatQuotedSnippet(quoted *waProto.Message, status bool) string {
	if quoted == nil {
		return ""
	}
	if plain := strings.TrimSpace(extractPlainText(quoted)); plain != "" {
		// One-line preview for the agent
		plain = strings.Join(strings.Fields(plain), " ")
		return truncateRunes(plain, 400)
	}
	switch {
	case quoted.GetImageMessage() != nil:
		if status {
			return "[imagem do status]"
		}
		return "[imagem]"
	case quoted.GetVideoMessage() != nil:
		if status {
			return "[vídeo do status]"
		}
		return "[vídeo]"
	case quoted.GetAudioMessage() != nil:
		return "[áudio]"
	case quoted.GetDocumentMessage() != nil:
		fn := strings.TrimSpace(quoted.GetDocumentMessage().GetFileName())
		if fn != "" {
			return "[documento: " + fn + "]"
		}
		return "[documento]"
	case quoted.GetStickerMessage() != nil:
		return "[sticker]"
	case quoted.GetLocationMessage() != nil, quoted.GetLiveLocationMessage() != nil:
		return "[localização]"
	case quoted.GetContactMessage() != nil:
		return "[contato]"
	default:
		return ""
	}
}

// quotedInlineThumbnail returns the JPEG preview embedded in a quoted image/video
// (no network). Status flyers almost always include this even when caption is empty.
func quotedInlineThumbnail(quoted *waProto.Message) []byte {
	if quoted == nil {
		return nil
	}
	if img := quoted.GetImageMessage(); img != nil {
		if t := img.GetJPEGThumbnail(); len(t) > 16 {
			return t
		}
	}
	if vid := quoted.GetVideoMessage(); vid != nil {
		if t := vid.GetJPEGThumbnail(); len(t) > 16 {
			return t
		}
	}
	return nil
}

func safeQuotedFilenameID(msgID string) string {
	if msgID == "" {
		return "unknown"
	}
	var b strings.Builder
	for _, r := range msgID {
		if (r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '_' || r == '-' {
			b.WriteRune(r)
		} else {
			b.WriteRune('_')
		}
	}
	out := b.String()
	if out == "" {
		return "unknown"
	}
	return out
}

// persistQuotedVisual writes the quoted image (full download, else JPEG thumbnail)
// next to other chat media so /api/download finds it. Used when the contact replies
// to a Status/flyer without sending their own photo.
func persistQuotedVisual(client *whatsmeow.Client, msg *waProto.Message, chatJID, msgID string) (mediaType, filename string) {
	if msg == nil || strings.TrimSpace(chatJID) == "" || strings.TrimSpace(msgID) == "" {
		return "", ""
	}
	ci := getContextInfo(msg)
	if ci == nil {
		return "", ""
	}
	quoted := ci.GetQuotedMessage()
	if quoted == nil {
		return "", ""
	}

	data := quotedInlineThumbnail(quoted)
	ext := ".jpg"
	mt := "image"
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if client != nil {
		if img := quoted.GetImageMessage(); img != nil {
			if full, err := client.Download(ctx, img); err == nil && len(full) > 16 {
				data = full
			}
		} else if vid := quoted.GetVideoMessage(); vid != nil {
			if full, err := client.Download(ctx, vid); err == nil && len(full) > 16 {
				data = full
				ext = ".mp4"
				mt = "video"
			}
		}
	}
	if len(data) < 16 {
		return "", ""
	}

	filename = "quoted_" + safeQuotedFilenameID(msgID) + ext
	chatDir := fmt.Sprintf("store/%s", strings.ReplaceAll(chatJID, ":", "_"))
	if err := os.MkdirAll(chatDir, 0755); err != nil {
		fmt.Printf("quoted visual mkdir %s: %v\n", chatDir, err)
		return "", ""
	}
	path := filepath.Join(chatDir, filename)
	if err := os.WriteFile(path, data, 0644); err != nil {
		fmt.Printf("quoted visual write %s: %v\n", path, err)
		return "", ""
	}
	fmt.Printf("Persisted quoted %s %s (%d bytes)\n", mt, path, len(data))
	return mt, filename
}

// extractTextContent returns body text, and when the person replied/quoted another
// message, prefixes "[citando: …]" so the agent and thread history see the context.
// Optional store+chatJID: if QuotedMessage payload is empty, look up stanzaID in SQLite.
func extractTextContent(msg *waProto.Message) string {
	return extractTextContentWithStore(msg, nil, "")
}

func extractTextContentWithStore(msg *waProto.Message, store *MessageStore, chatJID string) string {
	if msg == nil {
		return ""
	}
	body := strings.TrimSpace(extractPlainText(msg))
	if ad := formatAdContext(msg); ad != "" && !strings.Contains(body, ad) {
		if body == "" {
			body = ad
		} else {
			body = ad + "\n" + body
		}
	}

	quoteSnippet := ""
	if ci := getContextInfo(msg); ci != nil {
		status := isStatusQuote(ci)
		if qm := ci.GetQuotedMessage(); qm != nil {
			quoteSnippet = formatQuotedSnippet(qm, status)
		}
		// Fallback: WA sometimes omits full QuotedMessage but keeps stanzaID
		if quoteSnippet == "" && store != nil {
			if sid := strings.TrimSpace(ci.GetStanzaID()); sid != "" {
				if c, err := store.GetMessageContentByID(sid, chatJID); err == nil {
					c = strings.TrimSpace(c)
					// Strip a nested [citando:…] prefix if we already annotated the original
					if strings.HasPrefix(c, "[citando:") {
						if i := strings.Index(c, "]\n"); i >= 0 {
							c = strings.TrimSpace(c[i+2:])
						} else if i := strings.Index(c, "]"); i >= 0 {
							rest := strings.TrimSpace(c[i+1:])
							if rest != "" {
								c = rest
							}
						}
					}
					c = strings.Join(strings.Fields(c), " ")
					quoteSnippet = truncateRunes(c, 400)
				}
			}
		}
	}

	if quoteSnippet != "" {
		if body == "" {
			return "[citando: " + quoteSnippet + "]"
		}
		return "[citando: " + quoteSnippet + "]\n" + body
	}
	return body
}

// SendMessageResponse represents the response for the send message API
type SendMessageResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

// SendMessageRequest represents the request body for the send message API
type SendMessageRequest struct {
	Recipient string `json:"recipient"`
	Message   string `json:"message"`
	MediaPath string `json:"media_path,omitempty"`
	// Location pin (native WhatsApp map). If Latitude+Longitude set, sends LocationMessage.
	// Optional: location_name, location_address, location_url (Google Maps link).
	Latitude        *float64 `json:"latitude,omitempty"`
	Longitude       *float64 `json:"longitude,omitempty"`
	LocationName    string   `json:"location_name,omitempty"`
	LocationAddress string   `json:"location_address,omitempty"`
	LocationURL     string   `json:"location_url,omitempty"`
}

// resolveOutgoingChatJID picks the chat key we already use in messages.db.
// Many 1:1 chats are stored as @lid (via history/live events). Sending only to
// @s.whatsapp.net without persisting under the existing @lid chat makes /api/send
// invisible to the thread reader and splits the conversation.
func resolveOutgoingChatJID(client *whatsmeow.Client, messageStore *MessageStore, recipientJID types.JID) types.JID {
	// Prefer an existing chat row matching phone or lid.
	if messageStore != nil {
		phone := recipientJID.User
		if recipientJID.Server == types.DefaultUserServer || recipientJID.Server == "c.us" {
			// Look up LID mapping for this phone number.
			if client != nil && client.Store != nil && client.Store.LIDs != nil {
				if lid, err := client.Store.LIDs.GetLIDForPN(context.Background(), recipientJID); err == nil && !lid.IsEmpty() {
					lidStr := lid.String()
					var exists string
					if err := messageStore.db.QueryRow("SELECT jid FROM chats WHERE jid = ?", lidStr).Scan(&exists); err == nil && exists != "" {
						return lid
					}
					// Even without a prior chat row, prefer LID when mapped so future
					// inbound events (also on @lid) land in the same thread.
					return lid
				}
			}
			// Fallback: match chats by exact phone JID if present.
			phoneJID := recipientJID.ToNonAD().String()
			var exists string
			if err := messageStore.db.QueryRow("SELECT jid FROM chats WHERE jid = ? OR jid = ?", phoneJID, phone+"@s.whatsapp.net").Scan(&exists); err == nil && exists != "" {
				parsed, err := types.ParseJID(exists)
				if err == nil {
					return parsed
				}
			}
		}
		// If we already were given a @lid / existing JID, keep it when known.
		var exists string
		if err := messageStore.db.QueryRow("SELECT jid FROM chats WHERE jid = ?", recipientJID.ToNonAD().String()).Scan(&exists); err == nil && exists != "" {
			return recipientJID
		}
		_ = phone
	}
	return recipientJID
}

// TypingPresenceRequest body for /api/typing
type TypingPresenceRequest struct {
	Recipient string `json:"recipient"`
	// state: "composing" (digitando) | "paused" (parou)
	State string `json:"state"`
}

// sendChatPresence shows or clears "typing..." for a chat (best-effort).
func sendChatPresence(client *whatsmeow.Client, messageStore *MessageStore, recipient string, state string) (bool, string) {
	if !client.IsConnected() {
		return false, "Not connected to WhatsApp"
	}
	state = strings.ToLower(strings.TrimSpace(state))
	if state == "" || state == "typing" || state == "on" || state == "start" {
		state = "composing"
	}
	if state == "off" || state == "stop" || state == "clear" {
		state = "paused"
	}
	var chatState types.ChatPresence
	switch state {
	case "composing":
		chatState = types.ChatPresenceComposing
	case "paused":
		chatState = types.ChatPresencePaused
	default:
		return false, fmt.Sprintf("Invalid state %q (use composing|paused)", state)
	}

	var recipientJID types.JID
	var err error
	if strings.Contains(recipient, "@") {
		recipientJID, err = types.ParseJID(recipient)
		if err != nil {
			return false, fmt.Sprintf("Error parsing JID: %v", err)
		}
	} else {
		recipientJID = types.JID{User: recipient, Server: "s.whatsapp.net"}
	}
	// Prefer same chat key used for sends (@lid when mapped)
	recipientJID = resolveOutgoingChatJID(client, messageStore, recipientJID)

	err = client.SendChatPresence(context.Background(), recipientJID, chatState, types.ChatPresenceMediaText)
	if err != nil {
		return false, fmt.Sprintf("SendChatPresence error: %v", err)
	}
	return true, fmt.Sprintf("presence %s -> %s", state, recipientJID.String())
}

// Function to send a WhatsApp message
func sendWhatsAppMessage(client *whatsmeow.Client, messageStore *MessageStore, recipient string, message string, mediaPath string) (bool, string) {
	return sendWhatsAppMessageEx(client, messageStore, recipient, message, mediaPath, nil)
}

// locationPayload holds optional native map pin fields.
type locationPayload struct {
	Latitude  float64
	Longitude float64
	Name      string
	Address   string
	URL       string
}

func sendWhatsAppMessageEx(client *whatsmeow.Client, messageStore *MessageStore, recipient string, message string, mediaPath string, loc *locationPayload) (bool, string) {
	if !client.IsConnected() {
		return false, "Not connected to WhatsApp"
	}

	// Create JID for recipient
	var recipientJID types.JID
	var err error

	// Check if recipient is a JID
	isJID := strings.Contains(recipient, "@")

	if isJID {
		// Parse the JID string
		recipientJID, err = types.ParseJID(recipient)
		if err != nil {
			return false, fmt.Sprintf("Error parsing JID: %v", err)
		}
	} else {
		// Create JID from phone number
		recipientJID = types.JID{
			User:   recipient,
			Server: "s.whatsapp.net", // For personal chats
		}
	}

	msg := &waProto.Message{}
	mediaTypeStored := ""
	filenameStored := ""
	contentStored := message

	// Native location pin (takes precedence over plain text when lat/lng present)
	if loc != nil && (loc.Latitude != 0 || loc.Longitude != 0) {
		lat := loc.Latitude
		lng := loc.Longitude
		lm := &waProto.LocationMessage{
			DegreesLatitude:  &lat,
			DegreesLongitude: &lng,
		}
		if strings.TrimSpace(loc.Name) != "" {
			lm.Name = proto.String(strings.TrimSpace(loc.Name))
		}
		if strings.TrimSpace(loc.Address) != "" {
			lm.Address = proto.String(strings.TrimSpace(loc.Address))
		}
		if strings.TrimSpace(loc.URL) != "" {
			lm.URL = proto.String(strings.TrimSpace(loc.URL))
		}
		msg.LocationMessage = lm
		mediaTypeStored = "location"
		if contentStored == "" {
			parts := []string{}
			if loc.Name != "" {
				parts = append(parts, loc.Name)
			}
			if loc.Address != "" {
				parts = append(parts, loc.Address)
			}
			if len(parts) == 0 {
				contentStored = fmt.Sprintf("[location:%.6f,%.6f]", lat, lng)
			} else {
				contentStored = strings.Join(parts, " — ")
			}
		}
	} else if mediaPath != "" {
		// Read media file
		mediaData, err := os.ReadFile(mediaPath)
		if err != nil {
			return false, fmt.Sprintf("Error reading media file: %v", err)
		}

		// Determine media type and mime type based on file extension
		fileExt := strings.ToLower(mediaPath[strings.LastIndex(mediaPath, ".")+1:])
		var mediaType whatsmeow.MediaType
		var mimeType string

		// Handle different media types
		switch fileExt {
		// Image types
		case "jpg", "jpeg":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/jpeg"
			mediaTypeStored = "image"
		case "png":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/png"
			mediaTypeStored = "image"
		case "gif":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/gif"
			mediaTypeStored = "image"
		case "webp":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/webp"
			mediaTypeStored = "image"

		// Audio types
		case "ogg":
			mediaType = whatsmeow.MediaAudio
			mimeType = "audio/ogg; codecs=opus"
			mediaTypeStored = "audio"

		// Video types
		case "mp4":
			mediaType = whatsmeow.MediaVideo
			mimeType = "video/mp4"
			mediaTypeStored = "video"
		case "avi":
			mediaType = whatsmeow.MediaVideo
			mimeType = "video/avi"
			mediaTypeStored = "video"
		case "mov":
			mediaType = whatsmeow.MediaVideo
			mimeType = "video/quicktime"
			mediaTypeStored = "video"

		// Common document types — NEVER fall back to octet-stream for known office/docs
		// (WhatsApp shows octet-stream as "bin" and clients won't open as PDF).
		case "pdf":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/pdf"
			mediaTypeStored = "document"
		case "doc":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/msword"
			mediaTypeStored = "document"
		case "docx":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
			mediaTypeStored = "document"
		case "xls":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/vnd.ms-excel"
			mediaTypeStored = "document"
		case "xlsx":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
			mediaTypeStored = "document"
		case "ppt":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/vnd.ms-powerpoint"
			mediaTypeStored = "document"
		case "pptx":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
			mediaTypeStored = "document"
		case "txt", "md", "csv", "json", "xml", "html", "htm":
			mediaType = whatsmeow.MediaDocument
			mimeType = "text/plain"
			mediaTypeStored = "document"
		case "zip":
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/zip"
			mediaTypeStored = "document"

		// Document types (unknown extension)
		default:
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/octet-stream"
			mediaTypeStored = "document"
		}

		// Upload media to WhatsApp servers
		resp, err := client.Upload(context.Background(), mediaData, mediaType)
		if err != nil {
			return false, fmt.Sprintf("Error uploading media: %v", err)
		}

		fmt.Println("Media uploaded", resp)

		// Create the appropriate message type based on media type
		switch mediaType {
		case whatsmeow.MediaImage:
			msg.ImageMessage = &waProto.ImageMessage{
				Caption:       proto.String(message),
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
			}
		case whatsmeow.MediaAudio:
			// Handle ogg audio files
			var seconds uint32 = 30 // Default fallback
			var waveform []byte = nil

			// Try to analyze the ogg file
			if strings.Contains(mimeType, "ogg") {
				analyzedSeconds, analyzedWaveform, err := analyzeOggOpus(mediaData)
				if err == nil {
					seconds = analyzedSeconds
					waveform = analyzedWaveform
				} else {
					return false, fmt.Sprintf("Failed to analyze Ogg Opus file: %v", err)
				}
			} else {
				fmt.Printf("Not an Ogg Opus file: %s\n", mimeType)
			}

			msg.AudioMessage = &waProto.AudioMessage{
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
				Seconds:       proto.Uint32(seconds),
				PTT:           proto.Bool(true),
				Waveform:      waveform,
			}
		case whatsmeow.MediaVideo:
			msg.VideoMessage = &waProto.VideoMessage{
				Caption:       proto.String(message),
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
			}
		case whatsmeow.MediaDocument:
			filenameStored = mediaPath[strings.LastIndex(mediaPath, "/")+1:]
			if idx := strings.LastIndex(mediaPath, "\\"); idx >= 0 && idx+1 > strings.LastIndex(mediaPath, "/")+1 {
				filenameStored = mediaPath[idx+1:]
			}
			// FileName is what WhatsApp uses for the download name/extension.
			// Title alone is not enough — without FileName + correct mimetype
			// some clients show the file as generic "bin".
			msg.DocumentMessage = &waProto.DocumentMessage{
				Title:         proto.String(filenameStored),
				FileName:      proto.String(filenameStored),
				Caption:       proto.String(message),
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
			}
		}
	} else {
		if strings.TrimSpace(message) == "" {
			return false, "Message, media_path or location is required"
		}
		msg.Conversation = proto.String(message)
	}

	// Send message
	sendResp, err := client.SendMessage(context.Background(), recipientJID, msg)

	if err != nil {
		return false, fmt.Sprintf("Error sending message: %v", err)
	}

	// Persist outgoing message immediately. whatsmeow often does NOT re-emit a
	// local events.Message for API sends, so relying only on handleMessage leaves
	// business bubbles missing from messages.db.
	if messageStore != nil {
		chatJID := resolveOutgoingChatJID(client, messageStore, recipientJID)
		ts := sendResp.Timestamp
		if ts.IsZero() {
			ts = time.Now()
		}
		msgID := sendResp.ID
		if msgID == "" {
			msgID = fmt.Sprintf("local-%d", ts.UnixNano())
		}
		sender := ""
		if client.Store != nil && client.Store.ID != nil {
			sender = client.Store.ID.User
		}
		name := chatJID.User
		if err := messageStore.StoreChat(chatJID.String(), name, ts); err != nil {
			fmt.Printf("Warning: failed to store outgoing chat %s: %v\n", chatJID, err)
		}
		if err := messageStore.StoreMessage(
			msgID,
			chatJID.String(),
			sender,
			contentStored,
			ts,
			true, // is_from_me
			mediaTypeStored,
			filenameStored,
			"",
			nil,
			nil,
			nil,
			0,
		); err != nil {
			fmt.Printf("Warning: failed to store outgoing message %s: %v\n", msgID, err)
		} else {
			fmt.Printf("Stored outgoing message %s -> %s\n", msgID, chatJID.String())
		}
	}

	return true, fmt.Sprintf("Message sent to %s", recipient)
}

// Extract media info from a message
func extractMediaInfo(msg *waProto.Message) (mediaType string, filename string, url string, mediaKey []byte, fileSHA256 []byte, fileEncSHA256 []byte, fileLength uint64) {
	if msg == nil {
		return "", "", "", nil, nil, nil, 0
	}

	// Check for image message
	if img := msg.GetImageMessage(); img != nil {
		return "image", "image_" + time.Now().Format("20060102_150405") + ".jpg",
			img.GetURL(), img.GetMediaKey(), img.GetFileSHA256(), img.GetFileEncSHA256(), img.GetFileLength()
	}

	// Check for video message
	if vid := msg.GetVideoMessage(); vid != nil {
		return "video", "video_" + time.Now().Format("20060102_150405") + ".mp4",
			vid.GetURL(), vid.GetMediaKey(), vid.GetFileSHA256(), vid.GetFileEncSHA256(), vid.GetFileLength()
	}

	// Check for audio message
	if aud := msg.GetAudioMessage(); aud != nil {
		return "audio", "audio_" + time.Now().Format("20060102_150405") + ".ogg",
			aud.GetURL(), aud.GetMediaKey(), aud.GetFileSHA256(), aud.GetFileEncSHA256(), aud.GetFileLength()
	}

	// Check for document message
	if doc := msg.GetDocumentMessage(); doc != nil {
		filename := doc.GetFileName()
		if filename == "" {
			filename = "document_" + time.Now().Format("20060102_150405")
		}
		return "document", filename,
			doc.GetURL(), doc.GetMediaKey(), doc.GetFileSHA256(), doc.GetFileEncSHA256(), doc.GetFileLength()
	}

	// Shared contact (no downloadable media — content carries name/phone)
	if c := msg.GetContactMessage(); c != nil {
		fn := strings.TrimSpace(c.GetDisplayName())
		if fn == "" {
			fn = "contato"
		}
		return "contact", fn, "", nil, nil, nil, 0
	}

	return "", "", "", nil, nil, nil, 0
}

// IncomingWebhookPayload is POSTed to WA_WEBHOOK_URL on new 1:1 inbound messages.
// Used by router for debounce + classification + draft (never auto-send by default).
type IncomingWebhookPayload struct {
	Event     string `json:"event"`
	MessageID string `json:"message_id"`
	ChatJID   string `json:"chat_jid"`
	ChatName  string `json:"chat_name"`
	Sender    string `json:"sender"`
	Content   string `json:"content"`
	Timestamp string `json:"timestamp"`
	IsFromMe  bool   `json:"is_from_me"`
	MediaType string `json:"media_type,omitempty"`
	Filename  string `json:"filename,omitempty"`
	IsGroup   bool   `json:"is_group"`
	PushName  string `json:"push_name,omitempty"`
}

// postIncomingWebhook fires async HTTP POST. Failures are logged only — never block WhatsApp.
func postIncomingWebhook(payload IncomingWebhookPayload) {
	if os.Getenv("WA_WEBHOOK_DISABLED") == "1" || strings.EqualFold(os.Getenv("WA_WEBHOOK_DISABLED"), "true") {
		return
	}
	url := strings.TrimSpace(os.Getenv("WA_WEBHOOK_URL"))
	if url == "" {
		url = "http://127.0.0.1:8791/incoming"
	}

	body, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("Webhook marshal error: %v\n", err)
		return
	}

	client := &http.Client{Timeout: 2 * time.Second}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		fmt.Printf("Webhook request error: %v\n", err)
		return
	}
	req.Header.Set("Content-Type", "application/json; charset=utf-8")
	req.Header.Set("X-WA-Bridge-Event", "message")

	resp, err := client.Do(req)
	if err != nil {
		// Router offline is common during setup — keep quiet-ish
		fmt.Printf("Webhook POST failed (%s): %v\n", url, err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		fmt.Printf("Webhook POST status %d for %s\n", resp.StatusCode, payload.ChatJID)
	}
}

// Handle regular incoming messages with media support
func handleMessage(client *whatsmeow.Client, messageStore *MessageStore, msg *events.Message, logger waLog.Logger) {
	// Save message to database
	chatJID := msg.Info.Chat.String()
	sender := msg.Info.Sender.User
	isGroup := strings.HasSuffix(chatJID, "@g.us") || strings.HasSuffix(chatJID, "@broadcast") || strings.HasSuffix(chatJID, "@newsletter")

	// Get appropriate chat name (pass nil for conversation since we don't have one for regular messages)
	name := GetChatName(client, messageStore, msg.Info.Chat, chatJID, nil, sender, logger)

	// Update chat in database with the message timestamp (keeps last message time updated)
	err := messageStore.StoreChat(chatJID, name, msg.Info.Timestamp)
	if err != nil {
		logger.Warnf("Failed to store chat: %v", err)
	}

	// Extract text content (includes reply/quote context when present)
	content := extractTextContentWithStore(msg.Message, messageStore, chatJID)

	msgID := msg.Info.ID

	// Extract media info
	mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength := extractMediaInfo(msg.Message)
	// Reply to a Status/flyer: the person's bubble is text, but the quoted
	// image holds the course. Persist thumbnail (or full media) so the agent
	// can open the file instead of only seeing "[citando: [imagem]]".
	if mediaType == "" {
		if qmt, qfn := persistQuotedVisual(client, msg.Message, chatJID, msgID); qmt != "" {
			mediaType, filename = qmt, qfn
		}
	}

	// Skip if there's no content and no media
	if content == "" && mediaType == "" {
		return
	}
	// Check BEFORE store: StoreMessage is INSERT OR REPLACE, so a re-delivered
	// event would "succeed" and used to re-fire the router webhook (double reply).
	alreadyStored := false
	if msgID != "" {
		exists, herr := messageStore.HasMessage(msgID)
		if herr != nil {
			logger.Warnf("HasMessage(%s) failed: %v", msgID, herr)
		} else {
			alreadyStored = exists
		}
	}

	// Store message in database
	err = messageStore.StoreMessage(
		msgID,
		chatJID,
		sender,
		content,
		msg.Info.Timestamp,
		msg.Info.IsFromMe,
		mediaType,
		filename,
		url,
		mediaKey,
		fileSHA256,
		fileEncSHA256,
		fileLength,
	)

	if !msg.Info.IsFromMe {
		if ci := getContextInfo(msg.Message); ci != nil && ci.GetExternalAdReply() != nil {
			if aerr := messageStore.StoreAdClick(msgID, chatJID, sender, ci.GetExternalAdReply(), msg.Info.Timestamp); aerr != nil {
				logger.Warnf("Failed to store ad click: %v", aerr)
			}
		}
	}

	if err != nil {
		logger.Warnf("Failed to store message: %v", err)
	} else {
		// Log message reception
		timestamp := msg.Info.Timestamp.Format("2006-01-02 15:04:05")
		direction := "←"
		if msg.Info.IsFromMe {
			direction = "→"
		}

		// Log based on message type
		if mediaType != "" {
			fmt.Printf("[%s] %s %s: [%s: %s] %s\n", timestamp, direction, sender, mediaType, filename, content)
		} else if content != "" {
			fmt.Printf("[%s] %s %s: %s\n", timestamp, direction, sender, content)
		}

		// Event-driven hook for router: 1:1 inbound + outbound humano (from me).
		// Outbound: celular/app no mesmo WhatsApp — o painel precisa ver a resposta humana.
		// API sends do router já persistem no DB antes do event; alreadyStored evita
		// reclassificar auto-send como humano. Grupos nunca disparam webhook.
		// Skip if this message_id was already in SQLite (whatsmeow re-emit / retry).
		if !isGroup {
			if alreadyStored {
				fmt.Printf("Skip webhook (duplicate message_id %s) chat=%s\n", msgID, chatJID)
			} else {
				evName := "message.inbound"
				if msg.Info.IsFromMe {
					evName = "message.outbound"
				}
				payload := IncomingWebhookPayload{
					Event:     evName,
					MessageID: msgID,
					ChatJID:   chatJID,
					ChatName:  name,
					Sender:    sender,
					Content:   content,
					Timestamp: msg.Info.Timestamp.Format(time.RFC3339),
					IsFromMe:  msg.Info.IsFromMe,
					MediaType: mediaType,
					Filename:  filename,
					IsGroup:   false,
					PushName:  msg.Info.PushName,
				}
				go postIncomingWebhook(payload)
			}
		}
	}
}

// DownloadMediaRequest represents the request body for the download media API
type DownloadMediaRequest struct {
	MessageID string `json:"message_id"`
	ChatJID   string `json:"chat_jid"`
}

// DownloadMediaResponse represents the response for the download media API
type DownloadMediaResponse struct {
	Success  bool   `json:"success"`
	Message  string `json:"message"`
	Filename string `json:"filename,omitempty"`
	Path     string `json:"path,omitempty"`
}

// Store additional media info in the database
func (store *MessageStore) StoreMediaInfo(id, chatJID, url string, mediaKey, fileSHA256, fileEncSHA256 []byte, fileLength uint64) error {
	_, err := store.db.Exec(
		"UPDATE messages SET url = ?, media_key = ?, file_sha256 = ?, file_enc_sha256 = ?, file_length = ? WHERE id = ? AND chat_jid = ?",
		url, mediaKey, fileSHA256, fileEncSHA256, fileLength, id, chatJID,
	)
	return err
}

// Get media info from the database
func (store *MessageStore) GetMediaInfo(id, chatJID string) (string, string, string, []byte, []byte, []byte, uint64, error) {
	var mediaType, filename, url string
	var mediaKey, fileSHA256, fileEncSHA256 []byte
	var fileLength uint64

	err := store.db.QueryRow(
		"SELECT media_type, filename, url, media_key, file_sha256, file_enc_sha256, file_length FROM messages WHERE id = ? AND chat_jid = ?",
		id, chatJID,
	).Scan(&mediaType, &filename, &url, &mediaKey, &fileSHA256, &fileEncSHA256, &fileLength)

	return mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength, err
}

// MediaDownloader implements the whatsmeow.DownloadableMessage interface
type MediaDownloader struct {
	URL           string
	DirectPath    string
	MediaKey      []byte
	FileLength    uint64
	FileSHA256    []byte
	FileEncSHA256 []byte
	MediaType     whatsmeow.MediaType
}

// GetDirectPath implements the DownloadableMessage interface
func (d *MediaDownloader) GetDirectPath() string {
	return d.DirectPath
}

// GetURL implements the DownloadableMessage interface
func (d *MediaDownloader) GetURL() string {
	return d.URL
}

// GetMediaKey implements the DownloadableMessage interface
func (d *MediaDownloader) GetMediaKey() []byte {
	return d.MediaKey
}

// GetFileLength implements the DownloadableMessage interface
func (d *MediaDownloader) GetFileLength() uint64 {
	return d.FileLength
}

// GetFileSHA256 implements the DownloadableMessage interface
func (d *MediaDownloader) GetFileSHA256() []byte {
	return d.FileSHA256
}

// GetFileEncSHA256 implements the DownloadableMessage interface
func (d *MediaDownloader) GetFileEncSHA256() []byte {
	return d.FileEncSHA256
}

// GetMediaType implements the DownloadableMessage interface
func (d *MediaDownloader) GetMediaType() whatsmeow.MediaType {
	return d.MediaType
}

// Function to download media from a message
func downloadMedia(client *whatsmeow.Client, messageStore *MessageStore, messageID, chatJID string) (bool, string, string, string, error) {
	// Query the database for the message
	var mediaType, filename, url string
	var mediaKey, fileSHA256, fileEncSHA256 []byte
	var fileLength uint64
	var err error

	// First, check if we already have this file
	chatDir := fmt.Sprintf("store/%s", strings.ReplaceAll(chatJID, ":", "_"))
	localPath := ""

	// Get media info from the database
	mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength, err = messageStore.GetMediaInfo(messageID, chatJID)

	if err != nil {
		// Try to get basic info if extended info isn't available
		err = messageStore.db.QueryRow(
			"SELECT media_type, filename FROM messages WHERE id = ? AND chat_jid = ?",
			messageID, chatJID,
		).Scan(&mediaType, &filename)

		if err != nil {
			return false, "", "", "", fmt.Errorf("failed to find message: %v", err)
		}
	}

	// Check if this is a media message
	if mediaType == "" {
		return false, "", "", "", fmt.Errorf("not a media message")
	}

	// Create directory for the chat if it doesn't exist
	if err := os.MkdirAll(chatDir, 0755); err != nil {
		return false, "", "", "", fmt.Errorf("failed to create chat directory: %v", err)
	}

	// Generate a local path for the file
	localPath = fmt.Sprintf("%s/%s", chatDir, filename)

	// Get absolute path
	absPath, err := filepath.Abs(localPath)
	if err != nil {
		return false, "", "", "", fmt.Errorf("failed to get absolute path: %v", err)
	}

	// Check if file already exists
	if _, err := os.Stat(localPath); err == nil {
		// File exists, return it
		return true, mediaType, filename, absPath, nil
	}

	// If we don't have all the media info we need, we can't download
	if url == "" || len(mediaKey) == 0 || len(fileSHA256) == 0 || len(fileEncSHA256) == 0 || fileLength == 0 {
		return false, "", "", "", fmt.Errorf("incomplete media information for download")
	}

	fmt.Printf("Attempting to download media for message %s in chat %s...\n", messageID, chatJID)

	// Extract direct path from URL
	directPath := extractDirectPathFromURL(url)

	// Create a downloader that implements DownloadableMessage
	var waMediaType whatsmeow.MediaType
	switch mediaType {
	case "image":
		waMediaType = whatsmeow.MediaImage
	case "video":
		waMediaType = whatsmeow.MediaVideo
	case "audio":
		waMediaType = whatsmeow.MediaAudio
	case "document":
		waMediaType = whatsmeow.MediaDocument
	default:
		return false, "", "", "", fmt.Errorf("unsupported media type: %s", mediaType)
	}

	downloader := &MediaDownloader{
		URL:           url,
		DirectPath:    directPath,
		MediaKey:      mediaKey,
		FileLength:    fileLength,
		FileSHA256:    fileSHA256,
		FileEncSHA256: fileEncSHA256,
		MediaType:     waMediaType,
	}

	// Download the media using whatsmeow client
	mediaData, err := client.Download(context.Background(), downloader)
	if err != nil {
		return false, "", "", "", fmt.Errorf("failed to download media: %v", err)
	}

	// Save the downloaded media to file
	if err := os.WriteFile(localPath, mediaData, 0644); err != nil {
		return false, "", "", "", fmt.Errorf("failed to save media file: %v", err)
	}

	fmt.Printf("Successfully downloaded %s media to %s (%d bytes)\n", mediaType, absPath, len(mediaData))
	return true, mediaType, filename, absPath, nil
}

// Extract direct path from a WhatsApp media URL
func extractDirectPathFromURL(url string) string {
	// The direct path is typically in the URL, we need to extract it
	// Example URL: https://mmg.whatsapp.net/v/t62.7118-24/13812002_698058036224062_3424455886509161511_n.enc?ccb=11-4&oh=...

	// Find the path part after the domain
	parts := strings.SplitN(url, ".net/", 2)
	if len(parts) < 2 {
		return url // Return original URL if parsing fails
	}

	// Keep the full path WITH query parameters — WhatsApp requires them
	// for authentication (oh, oe, _nc_sid, etc.). Stripping them causes 403.
	return "/" + parts[1]
}

// Start a REST API server to expose the WhatsApp client functionality
func startRESTServer(client *whatsmeow.Client, messageStore *MessageStore, port int) {
	// Handler for sending messages
	http.HandleFunc("/api/send", func(w http.ResponseWriter, r *http.Request) {
		// Only allow POST requests
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Parse the request body
		var req SendMessageRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}

		// Validate request
		if req.Recipient == "" {
			http.Error(w, "Recipient is required", http.StatusBadRequest)
			return
		}

		hasLoc := req.Latitude != nil && req.Longitude != nil
		if req.Message == "" && req.MediaPath == "" && !hasLoc {
			http.Error(w, "Message, media_path or latitude+longitude is required", http.StatusBadRequest)
			return
		}

		fmt.Println("Received request to send message", req.Message, req.MediaPath, "loc=", hasLoc)

		var loc *locationPayload
		if hasLoc {
			loc = &locationPayload{
				Latitude:  *req.Latitude,
				Longitude: *req.Longitude,
				Name:      req.LocationName,
				Address:   req.LocationAddress,
				URL:       req.LocationURL,
			}
		}

		// Send the message (also persists to messages.db so the thread shows the business bubbles)
		success, message := sendWhatsAppMessageEx(client, messageStore, req.Recipient, req.Message, req.MediaPath, loc)
		fmt.Println("Message sent", success, message)
		// Set response headers
		w.Header().Set("Content-Type", "application/json")

		// Set appropriate status code
		if !success {
			w.WriteHeader(http.StatusInternalServerError)
		}

		// Send response
		json.NewEncoder(w).Encode(SendMessageResponse{
			Success: success,
			Message: message,
		})
	})

	// Handler for typing indicator (composing / paused)
	http.HandleFunc("/api/typing", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var req TypingPresenceRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}
		if req.Recipient == "" {
			http.Error(w, "Recipient is required", http.StatusBadRequest)
			return
		}
		success, message := sendChatPresence(client, messageStore, req.Recipient, req.State)
		w.Header().Set("Content-Type", "application/json")
		if !success {
			w.WriteHeader(http.StatusInternalServerError)
		}
		json.NewEncoder(w).Encode(SendMessageResponse{
			Success: success,
			Message: message,
		})
	})

	// Handler for downloading media
	http.HandleFunc("/api/download", func(w http.ResponseWriter, r *http.Request) {
		// Only allow POST requests
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Parse the request body
		var req DownloadMediaRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}

		// Validate request
		if req.MessageID == "" || req.ChatJID == "" {
			http.Error(w, "Message ID and Chat JID are required", http.StatusBadRequest)
			return
		}

		// Download the media
		success, mediaType, filename, path, err := downloadMedia(client, messageStore, req.MessageID, req.ChatJID)

		// Set response headers
		w.Header().Set("Content-Type", "application/json")

		// Handle download result
		if !success || err != nil {
			errMsg := "Unknown error"
			if err != nil {
				errMsg = err.Error()
			}

			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(DownloadMediaResponse{
				Success: false,
				Message: fmt.Sprintf("Failed to download media: %s", errMsg),
			})
			return
		}

		// Send successful response
		json.NewEncoder(w).Encode(DownloadMediaResponse{
			Success:  true,
			Message:  fmt.Sprintf("Successfully downloaded %s media", mediaType),
			Filename: filename,
			Path:     path,
		})
	})

	// Start the server
	serverAddr := fmt.Sprintf(":%d", port)
	fmt.Printf("Starting REST API server on %s...\n", serverAddr)

	// Run server in a goroutine so it doesn't block
	go func() {
		if err := http.ListenAndServe(serverAddr, nil); err != nil {
			fmt.Printf("REST API server error: %v\n", err)
		}
	}()
}

func main() {
	// Set up logger
	logger := waLog.Stdout("Client", "INFO", true)
	logger.Infof("Starting WhatsApp client...")
	// The advertised WhatsApp Web version expires independently of this binary.
	versionCtx, cancelVersion := context.WithTimeout(context.Background(), 20*time.Second)
	latestVersion, versionErr := whatsmeow.GetLatestVersion(versionCtx, nil)
	cancelVersion()
	if versionErr != nil {
		logger.Warnf("Unable to refresh WhatsApp Web version: %v", versionErr)
	} else {
		store.SetWAVersion(*latestVersion)
		logger.Infof("Using WhatsApp Web version %s", latestVersion.String())
	}

	// Create database connection for storing session data
	dbLog := waLog.Stdout("Database", "INFO", true)

	// Create directory for database if it doesn't exist
	if err := os.MkdirAll("store", 0755); err != nil {
		logger.Errorf("Failed to create store directory: %v", err)
		return
	}

	container, err := sqlstore.New(context.Background(), "sqlite3", "file:store/whatsapp.db?_foreign_keys=on", dbLog)
	if err != nil {
		logger.Errorf("Failed to connect to database: %v", err)
		return
	}

	// Get device store - This contains session information
	deviceStore, err := container.GetFirstDevice(context.Background())
	if err != nil {
		if err == sql.ErrNoRows {
			// No device exists, create one
			deviceStore = container.NewDevice()
			logger.Infof("Created new device")
		} else {
			logger.Errorf("Failed to get device: %v", err)
			return
		}
	}

	// Create client instance
	client := whatsmeow.NewClient(deviceStore, logger)
	if client == nil {
		logger.Errorf("Failed to create WhatsApp client")
		return
	}

	// Initialize message store
	messageStore, err := NewMessageStore()
	if err != nil {
		logger.Errorf("Failed to initialize message store: %v", err)
		return
	}
	defer messageStore.Close()

	// Setup event handling for messages and history sync
	client.AddEventHandler(func(evt interface{}) {
		switch v := evt.(type) {
		case *events.Message:
			// Process regular messages
			handleMessage(client, messageStore, v, logger)

		case *events.HistorySync:
			// Process history sync events
			handleHistorySync(client, messageStore, v, logger)

		case *events.Connected:
			logger.Infof("Connected to WhatsApp")

		case *events.LoggedOut:
			logger.Warnf("Device logged out, please scan QR code to log in again")
		}
	})

	// Create channel to track connection success
	connected := make(chan bool, 1)

	// Connect to WhatsApp
	if client.Store.ID == nil {
		// No ID stored, this is a new client, need to pair with phone
		qrChan, _ := client.GetQRChannel(context.Background())
		err = client.Connect()
		if err != nil {
			logger.Errorf("Failed to connect: %v", err)
			return
		}

		// Print QR code for pairing with phone
		for evt := range qrChan {
			if evt.Event == "code" {
				fmt.Println("\nScan this QR code with your WhatsApp app:")
				qrterminal.GenerateHalfBlock(evt.Code, qrterminal.L, os.Stdout)
			} else if evt.Event == "success" {
				connected <- true
				break
			}
		}

		// Wait for connection
		select {
		case <-connected:
			fmt.Println("\nSuccessfully connected and authenticated!")
		case <-time.After(3 * time.Minute):
			logger.Errorf("Timeout waiting for QR code scan")
			return
		}
	} else {
		// Already logged in, just connect
		err = client.Connect()
		if err != nil {
			logger.Errorf("Failed to connect: %v", err)
			return
		}
		connected <- true
	}

	// Wait a moment for connection to stabilize
	time.Sleep(2 * time.Second)

	if !client.IsConnected() {
		logger.Errorf("Failed to establish stable connection")
		return
	}

	fmt.Println("\n✓ Connected to WhatsApp! Type 'help' for commands.")

	// Start REST API server
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		connected := client.IsConnected()
		loggedIn := client.IsLoggedIn()
		w.Header().Set("Content-Type", "application/json")
		if !connected || !loggedIn {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
		json.NewEncoder(w).Encode(map[string]interface{}{
			"ok": connected && loggedIn, "connected": connected, "logged_in": loggedIn,
			"version": store.GetWAVersion().String(),
		})
	})
	startRESTServer(client, messageStore, 8080)

	// Create a channel to keep the main goroutine alive
	exitChan := make(chan os.Signal, 1)
	signal.Notify(exitChan, syscall.SIGINT, syscall.SIGTERM)

	fmt.Println("REST server is running. Press Ctrl+C to disconnect and exit.")

	// Wait for termination signal
	<-exitChan

	fmt.Println("Disconnecting...")
	// Disconnect client
	client.Disconnect()
}

// GetChatName determines the appropriate name for a chat based on JID and other info
func GetChatName(client *whatsmeow.Client, messageStore *MessageStore, jid types.JID, chatJID string, conversation interface{}, sender string, logger waLog.Logger) string {
	// First, check if chat already exists in database with a name
	var existingName string
	err := messageStore.db.QueryRow("SELECT name FROM chats WHERE jid = ?", chatJID).Scan(&existingName)
	if err == nil && existingName != "" {
		// Chat exists with a name, use that
		logger.Infof("Using existing chat name for %s: %s", chatJID, existingName)
		return existingName
	}

	// Need to determine chat name
	var name string

	if jid.Server == "g.us" {
		// This is a group chat
		logger.Infof("Getting name for group: %s", chatJID)

		// Use conversation data if provided (from history sync)
		if conversation != nil {
			// Extract name from conversation if available
			// This uses type assertions to handle different possible types
			var displayName, convName *string
			// Try to extract the fields we care about regardless of the exact type
			v := reflect.ValueOf(conversation)
			if v.Kind() == reflect.Ptr && !v.IsNil() {
				v = v.Elem()

				// Try to find DisplayName field
				if displayNameField := v.FieldByName("DisplayName"); displayNameField.IsValid() && displayNameField.Kind() == reflect.Ptr && !displayNameField.IsNil() {
					dn := displayNameField.Elem().String()
					displayName = &dn
				}

				// Try to find Name field
				if nameField := v.FieldByName("Name"); nameField.IsValid() && nameField.Kind() == reflect.Ptr && !nameField.IsNil() {
					n := nameField.Elem().String()
					convName = &n
				}
			}

			// Use the name we found
			if displayName != nil && *displayName != "" {
				name = *displayName
			} else if convName != nil && *convName != "" {
				name = *convName
			}
		}

		// If we didn't get a name, try group info
		if name == "" {
			groupInfo, err := client.GetGroupInfo(context.Background(), jid)
			if err == nil && groupInfo.Name != "" {
				name = groupInfo.Name
			} else {
				// Fallback name for groups
				name = fmt.Sprintf("Group %s", jid.User)
			}
		}

		logger.Infof("Using group name: %s", name)
	} else {
		// This is an individual contact
		logger.Infof("Getting name for contact: %s", chatJID)

		// Just use contact info (full name)
		contact, err := client.Store.Contacts.GetContact(context.Background(), jid)
		if err == nil && contact.FullName != "" {
			name = contact.FullName
		} else if sender != "" {
			// Fallback to sender
			name = sender
		} else {
			// Last fallback to JID
			name = jid.User
		}

		// If name is still just a number and this is a @lid contact,
		// try to resolve the LID to phone number and look up the real name
		if jid.Server == "lid" && (name == jid.User || name == sender) {
			logger.Infof("LID contact without real name, trying LID→PN resolution for %s", jid.User)
			whatsappDB, err := sql.Open("sqlite3", "file:store/whatsapp.db?_foreign_keys=on")
			if err == nil {
				var pn string
				err = whatsappDB.QueryRow(
					"SELECT pn FROM whatsmeow_lid_map WHERE lid = ?", jid.User,
				).Scan(&pn)
				if err == nil && pn != "" {
					pnJID := types.JID{User: pn, Server: "s.whatsapp.net"}
					pnContact, err := client.Store.Contacts.GetContact(context.Background(), pnJID)
					if err == nil && pnContact.FullName != "" {
						name = pnContact.FullName
						logger.Infof("Resolved LID %s → PN %s → name '%s'", jid.User, pn, name)
					}
				}
				whatsappDB.Close()
			}
		}

		logger.Infof("Using contact name: %s", name)
	}

	return name
}

// Handle history sync events
func handleHistorySync(client *whatsmeow.Client, messageStore *MessageStore, historySync *events.HistorySync, logger waLog.Logger) {
	fmt.Printf("Received history sync event with %d conversations\n", len(historySync.Data.Conversations))

	syncedCount := 0
	for _, conversation := range historySync.Data.Conversations {
		// Parse JID from the conversation
		if conversation.ID == nil {
			continue
		}

		chatJID := *conversation.ID

		// Try to parse the JID
		jid, err := types.ParseJID(chatJID)
		if err != nil {
			logger.Warnf("Failed to parse JID %s: %v", chatJID, err)
			continue
		}

		// Get appropriate chat name by passing the history sync conversation directly
		name := GetChatName(client, messageStore, jid, chatJID, conversation, "", logger)

		// Process messages
		messages := conversation.Messages
		if len(messages) > 0 {
			// Update chat with latest message timestamp
			latestMsg := messages[0]
			if latestMsg == nil || latestMsg.Message == nil {
				continue
			}

			// Get timestamp from message info
			timestamp := time.Time{}
			if ts := latestMsg.Message.GetMessageTimestamp(); ts != 0 {
				timestamp = time.Unix(int64(ts), 0)
			} else {
				continue
			}

			messageStore.StoreChat(chatJID, name, timestamp)

			// Store messages
			for _, msg := range messages {
				if msg == nil || msg.Message == nil {
					continue
				}

				// Extract text content (incl. quoted/reply context + captions)
				var content string
				if msg.Message.Message != nil {
					content = extractTextContentWithStore(msg.Message.Message, messageStore, chatJID)
				}

				// Extract media info
				var mediaType, filename, url string
				var mediaKey, fileSHA256, fileEncSHA256 []byte
				var fileLength uint64

				if msg.Message.Message != nil {
					mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength = extractMediaInfo(msg.Message.Message)
				}
				if mediaType == "" && msg.Message.Message != nil {
					hid := ""
					if msg.Message.Key != nil && msg.Message.Key.ID != nil {
						hid = *msg.Message.Key.ID
					}
					if qmt, qfn := persistQuotedVisual(client, msg.Message.Message, chatJID, hid); qmt != "" {
						mediaType, filename = qmt, qfn
					}
				}

				// Log the message content for debugging
				logger.Infof("Message content: %v, Media Type: %v", content, mediaType)

				// Skip messages with no content and no media
				if content == "" && mediaType == "" {
					continue
				}

				// Determine sender
				var sender string
				isFromMe := false
				if msg.Message.Key != nil {
					if msg.Message.Key.FromMe != nil {
						isFromMe = *msg.Message.Key.FromMe
					}
					if !isFromMe && msg.Message.Key.Participant != nil && *msg.Message.Key.Participant != "" {
						sender = *msg.Message.Key.Participant
					} else if isFromMe {
						sender = client.Store.ID.User
					} else {
						sender = jid.User
					}
				} else {
					sender = jid.User
				}

				// Store message
				msgID := ""
				if msg.Message.Key != nil && msg.Message.Key.ID != nil {
					msgID = *msg.Message.Key.ID
				}

				// Get message timestamp
				timestamp := time.Time{}
				if ts := msg.Message.GetMessageTimestamp(); ts != 0 {
					timestamp = time.Unix(int64(ts), 0)
				} else {
					continue
				}

				err = messageStore.StoreMessage(
					msgID,
					chatJID,
					sender,
					content,
					timestamp,
					isFromMe,
					mediaType,
					filename,
					url,
					mediaKey,
					fileSHA256,
					fileEncSHA256,
					fileLength,
				)
				if err != nil {
					logger.Warnf("Failed to store history message: %v", err)
				} else {
					syncedCount++
					// Log successful message storage
					if mediaType != "" {
						logger.Infof("Stored message: [%s] %s -> %s: [%s: %s] %s",
							timestamp.Format("2006-01-02 15:04:05"), sender, chatJID, mediaType, filename, content)
					} else {
						logger.Infof("Stored message: [%s] %s -> %s: %s",
							timestamp.Format("2006-01-02 15:04:05"), sender, chatJID, content)
					}
				}
			}
		}
	}

	fmt.Printf("History sync complete. Stored %d messages.\n", syncedCount)
}

// Request history sync from the server
func requestHistorySync(client *whatsmeow.Client) {
	if client == nil {
		fmt.Println("Client is not initialized. Cannot request history sync.")
		return
	}

	if !client.IsConnected() {
		fmt.Println("Client is not connected. Please ensure you are connected to WhatsApp first.")
		return
	}

	if client.Store.ID == nil {
		fmt.Println("Client is not logged in. Please scan the QR code first.")
		return
	}

	// Build and send a history sync request
	historyMsg := client.BuildHistorySyncRequest(nil, 100)
	if historyMsg == nil {
		fmt.Println("Failed to build history sync request.")
		return
	}

	_, err := client.SendMessage(context.Background(), types.JID{
		Server: "s.whatsapp.net",
		User:   "status",
	}, historyMsg)

	if err != nil {
		fmt.Printf("Failed to request history sync: %v\n", err)
	} else {
		fmt.Println("History sync requested. Waiting for server response...")
	}
}

// analyzeOggOpus tries to extract duration and generate a simple waveform from an Ogg Opus file
func analyzeOggOpus(data []byte) (duration uint32, waveform []byte, err error) {
	// Try to detect if this is a valid Ogg file by checking for the "OggS" signature
	// at the beginning of the file
	if len(data) < 4 || string(data[0:4]) != "OggS" {
		return 0, nil, fmt.Errorf("not a valid Ogg file (missing OggS signature)")
	}

	// Parse Ogg pages to find the last page with a valid granule position
	var lastGranule uint64
	var sampleRate uint32 = 48000 // Default Opus sample rate
	var preSkip uint16 = 0
	var foundOpusHead bool

	// Scan through the file looking for Ogg pages
	for i := 0; i < len(data); {
		// Check if we have enough data to read Ogg page header
		if i+27 >= len(data) {
			break
		}

		// Verify Ogg page signature
		if string(data[i:i+4]) != "OggS" {
			// Skip until next potential page
			i++
			continue
		}

		// Extract header fields
		granulePos := binary.LittleEndian.Uint64(data[i+6 : i+14])
		pageSeqNum := binary.LittleEndian.Uint32(data[i+18 : i+22])
		numSegments := int(data[i+26])

		// Extract segment table
		if i+27+numSegments >= len(data) {
			break
		}
		segmentTable := data[i+27 : i+27+numSegments]

		// Calculate page size
		pageSize := 27 + numSegments
		for _, segLen := range segmentTable {
			pageSize += int(segLen)
		}

		// Check if we're looking at an OpusHead packet (should be in first few pages)
		if !foundOpusHead && pageSeqNum <= 1 {
			// Look for "OpusHead" marker in this page
			pageData := data[i : i+pageSize]
			headPos := bytes.Index(pageData, []byte("OpusHead"))
			if headPos >= 0 && headPos+12 < len(pageData) {
				// Found OpusHead, extract sample rate and pre-skip
				// OpusHead format: Magic(8) + Version(1) + Channels(1) + PreSkip(2) + SampleRate(4) + ...
				headPos += 8 // Skip "OpusHead" marker
				// PreSkip is 2 bytes at offset 10
				if headPos+12 <= len(pageData) {
					preSkip = binary.LittleEndian.Uint16(pageData[headPos+10 : headPos+12])
					sampleRate = binary.LittleEndian.Uint32(pageData[headPos+12 : headPos+16])
					foundOpusHead = true
					fmt.Printf("Found OpusHead: sampleRate=%d, preSkip=%d\n", sampleRate, preSkip)
				}
			}
		}

		// Keep track of last valid granule position
		if granulePos != 0 {
			lastGranule = granulePos
		}

		// Move to next page
		i += pageSize
	}

	if !foundOpusHead {
		fmt.Println("Warning: OpusHead not found, using default values")
	}

	// Calculate duration based on granule position
	if lastGranule > 0 {
		// Formula for duration: (lastGranule - preSkip) / sampleRate
		durationSeconds := float64(lastGranule-uint64(preSkip)) / float64(sampleRate)
		duration = uint32(math.Ceil(durationSeconds))
		fmt.Printf("Calculated Opus duration from granule: %f seconds (lastGranule=%d)\n",
			durationSeconds, lastGranule)
	} else {
		// Fallback to rough estimation if granule position not found
		fmt.Println("Warning: No valid granule position found, using estimation")
		durationEstimate := float64(len(data)) / 2000.0 // Very rough approximation
		duration = uint32(durationEstimate)
	}

	// Make sure we have a reasonable duration (at least 1 second, at most 300 seconds)
	if duration < 1 {
		duration = 1
	} else if duration > 300 {
		duration = 300
	}

	// Generate waveform
	waveform = placeholderWaveform(duration)

	fmt.Printf("Ogg Opus analysis: size=%d bytes, calculated duration=%d sec, waveform=%d bytes\n",
		len(data), duration, len(waveform))

	return duration, waveform, nil
}

// min returns the smaller of x or y
func min(x, y int) int {
	if x < y {
		return x
	}
	return y
}

// placeholderWaveform generates a synthetic waveform for WhatsApp voice messages
// that appears natural with some variability based on the duration
func placeholderWaveform(duration uint32) []byte {
	// WhatsApp expects a 64-byte waveform for voice messages
	const waveformLength = 64
	waveform := make([]byte, waveformLength)

	// Seed the random number generator for consistent results with the same duration
	rand.Seed(int64(duration))

	// Create a more natural looking waveform with some patterns and variability
	// rather than completely random values

	// Base amplitude and frequency - longer messages get faster frequency
	baseAmplitude := 35.0
	frequencyFactor := float64(min(int(duration), 120)) / 30.0

	for i := range waveform {
		// Position in the waveform (normalized 0-1)
		pos := float64(i) / float64(waveformLength)

		// Create a wave pattern with some randomness
		// Use multiple sine waves of different frequencies for more natural look
		val := baseAmplitude * math.Sin(pos*math.Pi*frequencyFactor*8)
		val += (baseAmplitude / 2) * math.Sin(pos*math.Pi*frequencyFactor*16)

		// Add some randomness to make it look more natural
		val += (rand.Float64() - 0.5) * 15

		// Add some fade-in and fade-out effects
		fadeInOut := math.Sin(pos * math.Pi)
		val = val * (0.7 + 0.3*fadeInOut)

		// Center around 50 (typical voice baseline)
		val = val + 50

		// Ensure values stay within WhatsApp's expected range (0-100)
		if val < 0 {
			val = 0
		} else if val > 100 {
			val = 100
		}

		waveform[i] = byte(val)
	}

	return waveform
}
