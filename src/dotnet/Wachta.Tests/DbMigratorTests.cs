using Npgsql;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class DbMigratorTests(PostgresFixture db)
{
    [DockerTheory]
    [InlineData("source")]
    [InlineData("fetch_log")]
    [InlineData("aircraft_position")]
    [InlineData("alert")]
    [InlineData("jamming_cell")]
    [InlineData("coverage_hourly")]
    public async Task Migration_creates_table(string table)
    {
        await using var conn = new NpgsqlConnection(db.ConnectionString);
        await conn.OpenAsync();
        await using var cmd = new NpgsqlCommand("SELECT to_regclass(@t) IS NOT NULL", conn);
        cmd.Parameters.AddWithValue("t", table);
        Assert.True((bool)(await cmd.ExecuteScalarAsync())!);
    }

    [DockerFact]
    public async Task Aircraft_position_is_hypertable()
    {
        await using var conn = new NpgsqlConnection(db.ConnectionString);
        await conn.OpenAsync();
        await using var cmd = new NpgsqlCommand(
            "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'aircraft_position'", conn);
        Assert.Equal(1L, (long)(await cmd.ExecuteScalarAsync())!);
    }

    [DockerFact]
    public void Migration_is_idempotent()
    {
        Wachta.Db.DbMigrator.Migrate(db.ConnectionString);
    }
}
