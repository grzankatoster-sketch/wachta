using Npgsql;
using NpgsqlTypes;
using Wachta.Domain;

namespace Wachta.Ingestion;

public interface IPositionWriter
{
    Task<int> WriteAsync(SourceSnapshot snapshot, IReadOnlyList<AircraftObservation> rows, CancellationToken ct);
}

/// <summary>Repository: writes positions with binary COPY (fast bulk insert) and one fetch_log row per fetch.</summary>
public sealed class PositionWriter(NpgsqlDataSource db) : IPositionWriter
{
    private const string CopySql =
        "COPY aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground, " +
        "gs_kt, track_deg, nic, nac_p, source_id, fetched_at) FROM STDIN (FORMAT BINARY)";

    public async Task<int> WriteAsync(SourceSnapshot snapshot, IReadOnlyList<AircraftObservation> rows, CancellationToken ct)
    {
        await using var conn = await db.OpenConnectionAsync(ct);
        await using var tx = await conn.BeginTransactionAsync(ct);

        if (rows.Count > 0)
        {
            await using var copy = await conn.BeginBinaryImportAsync(CopySql, ct);
            foreach (var r in rows)
            {
                await copy.StartRowAsync(ct);
                await copy.WriteAsync(r.Timestamp.UtcDateTime, NpgsqlDbType.TimestampTz, ct);
                await copy.WriteAsync(r.Hex, NpgsqlDbType.Text, ct);
                await WriteNullable(copy, r.Flight, NpgsqlDbType.Text, ct);
                await WriteNullable(copy, r.TypeCode, NpgsqlDbType.Text, ct);
                await copy.WriteAsync(r.IsMilitary, NpgsqlDbType.Boolean, ct);
                await copy.WriteAsync(r.Lat, NpgsqlDbType.Double, ct);
                await copy.WriteAsync(r.Lon, NpgsqlDbType.Double, ct);
                await WriteNullable(copy, r.AltBaroFt, NpgsqlDbType.Integer, ct);
                await copy.WriteAsync(r.OnGround, NpgsqlDbType.Boolean, ct);
                await WriteNullable(copy, r.GroundSpeedKt, NpgsqlDbType.Real, ct);
                await WriteNullable(copy, r.TrackDeg, NpgsqlDbType.Real, ct);
                await WriteNullable(copy, r.Nic, NpgsqlDbType.Smallint, ct);
                await WriteNullable(copy, r.NacP, NpgsqlDbType.Smallint, ct);
                await copy.WriteAsync(snapshot.SourceId, NpgsqlDbType.Text, ct);
                await copy.WriteAsync(snapshot.FetchedAt.UtcDateTime, NpgsqlDbType.TimestampTz, ct);
            }

            await copy.CompleteAsync(ct);
        }

        if (snapshot.Contacts.Count > 0)
        {
            await using var contacts = new NpgsqlCommand("""
                INSERT INTO aircraft_contact (hex, last_message_at, last_position_at, source_id, updated_at)
                SELECT h, m, p, @src, @upd FROM unnest(@hex, @msg, @pos) AS t(h, m, p)
                ON CONFLICT (hex) DO UPDATE SET
                    last_message_at  = GREATEST(aircraft_contact.last_message_at, EXCLUDED.last_message_at),
                    last_position_at = GREATEST(aircraft_contact.last_position_at, EXCLUDED.last_position_at),
                    source_id = EXCLUDED.source_id,
                    updated_at = EXCLUDED.updated_at
                """, conn, tx);
            contacts.Parameters.AddWithValue("hex", snapshot.Contacts.Select(c => c.Hex).ToArray());
            contacts.Parameters.AddWithValue("msg", snapshot.Contacts.Select(c => c.LastMessageAt.UtcDateTime).ToArray());
            // DateTime?[] maps to timestamptz[] with real NULLs; an object[] with DBNull does not.
            contacts.Parameters.AddWithValue("pos", snapshot.Contacts.Select(c => c.LastPositionAt?.UtcDateTime).ToArray());
            contacts.Parameters.AddWithValue("src", snapshot.SourceId);
            contacts.Parameters.AddWithValue("upd", snapshot.FetchedAt.UtcDateTime);
            await contacts.ExecuteNonQueryAsync(ct);
        }

        await using (var log = new NpgsqlCommand(
            "INSERT INTO fetch_log (source_id, url, fetched_at, content_hash, n_received, n_written) " +
            "VALUES (@s, @u, @f, @h, @nr, @nw)", conn, tx))
        {
            log.Parameters.AddWithValue("s", snapshot.SourceId);
            log.Parameters.AddWithValue("u", snapshot.Url.ToString());
            log.Parameters.AddWithValue("f", snapshot.FetchedAt.UtcDateTime);
            log.Parameters.AddWithValue("h", snapshot.ContentHash);
            log.Parameters.AddWithValue("nr", snapshot.Aircraft.Count);
            log.Parameters.AddWithValue("nw", rows.Count);
            await log.ExecuteNonQueryAsync(ct);
        }

        await tx.CommitAsync(ct);
        return rows.Count;
    }

    private static async Task WriteNullable<T>(NpgsqlBinaryImporter copy, T? value, NpgsqlDbType type, CancellationToken ct)
    {
        if (value is null)
        {
            await copy.WriteNullAsync(ct);
        }
        else
        {
            await copy.WriteAsync(value, type, ct);
        }
    }
}
