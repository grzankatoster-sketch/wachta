using Testcontainers.PostgreSql;
using Wachta.Db;

namespace Wachta.Tests;

public sealed class PostgresFixture : IAsyncLifetime
{
    /// <summary>Ten sam obraz co w compose.yaml. Test na innej wersji bazy niz produkcja sprawdza
    /// inna baze niz ta, ktora pojedzie - a TimescaleDB i PostGIS to nie detale.</summary>
    private const string Image = "timescale/timescaledb-ha:pg17";

    // Kontener powstaje dopiero w InitializeAsync, a nie przy tworzeniu pola: samo zbudowanie go
    // szuka gniazda Dockera i wybucha, zanim ktorykolwiek test zdazy sie pominac.
    private PostgreSqlContainer? _container;

    public string ConnectionString => _container?.GetConnectionString()
        ?? throw new InvalidOperationException(DockerAvailable.Reason ?? "kontener nie wystartowal");

    public async Task InitializeAsync()
    {
        if (!DockerAvailable.Yes)
        {
            return;     // testy tej kolekcji i tak sa pominiete - nie ma czego uruchamiac
        }

        // Obraz idzie do konstruktora, bo bezargumentowy jest juz przestarzaly w Testcontainers.
        _container = new PostgreSqlBuilder(Image)
            .WithDatabase("wachta")
            .WithUsername("postgres")
            .WithPassword("postgres")
            .Build();
        await _container.StartAsync();
        DbMigrator.Migrate(ConnectionString);
    }

    public Task DisposeAsync() => _container?.DisposeAsync().AsTask() ?? Task.CompletedTask;
}

[CollectionDefinition("postgres")]
public sealed class PostgresCollection : ICollectionFixture<PostgresFixture>;
