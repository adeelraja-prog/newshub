// Stores the WhatsApp login in MongoDB so it survives free-host restarts.
import { BufferJSON, initAuthCreds, proto } from "@whiskeysockets/baileys";

export async function useMongoAuthState(coll) {
  const write = (data, id) =>
    coll.replaceOne({ _id: id }, { _id: id, v: JSON.stringify(data, BufferJSON.replacer) }, { upsert: true });
  const read = async (id) => {
    const doc = await coll.findOne({ _id: id });
    return doc ? JSON.parse(doc.v, BufferJSON.reviver) : null;
  };
  const remove = (id) => coll.deleteOne({ _id: id });

  const creds = (await read("creds")) || initAuthCreds();

  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          const data = {};
          await Promise.all(
            ids.map(async (id) => {
              let value = await read(`${type}-${id}`);
              if (type === "app-state-sync-key" && value) {
                value = proto.Message.AppStateSyncKeyData.fromObject(value);
              }
              data[id] = value;
            })
          );
          return data;
        },
        set: async (data) => {
          const tasks = [];
          for (const category of Object.keys(data)) {
            for (const id of Object.keys(data[category])) {
              const value = data[category][id];
              tasks.push(value ? write(value, `${category}-${id}`) : remove(`${category}-${id}`));
            }
          }
          await Promise.all(tasks);
        },
      },
    },
    saveCreds: () => write(creds, "creds"),
    clear: () => coll.deleteMany({}),
  };
}
